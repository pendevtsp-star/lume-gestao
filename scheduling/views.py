from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone as datetime_timezone
from uuid import uuid4

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import FinanceAccessMixin, RoleRequiredMixin, get_profile
from core.deletion import (
    DELETE_ACTION_NOW,
    DeletionDecisionMixin,
    hard_delete_availability,
    hard_delete_service_package,
    mark_active_object_for_deletion,
    mark_package_for_deletion,
)
from core.models import ClinicSettings
from core.views import FormContextMixin, SearchableListView
from patients.models import Patient
from scheduling.forms import (
    AgendaSettingsForm,
    AppointmentAttendanceForm,
    AppointmentForm,
    AppointmentRescheduleSlotForm,
    AppointmentSlotSearchForm,
    PatientCheckInForm,
    PatientGoalForm,
    ProfessionalAvailabilityForm,
    ProfessionalAvailabilityBatchForm,
    RescheduleRequestForm,
    ServicePackageForm,
)
from scheduling.models import (
    Appointment,
    AppointmentAttendance,
    AppointmentSeries,
    PatientCheckIn,
    PatientGoal,
    PatientNotification,
    ProfessionalAvailability,
    RescheduleRequest,
    ServicePackage,
    ServicePackageAdjustment,
    ServiceUsage,
)
from scheduling.services import (
    completion_needs_credit_adjustment,
    completion_package_for_appointment,
    ensure_credit_for_appointment,
    generate_operational_notifications,
    mark_absence,
    patient_monthly_summary,
    record_attendance_for_canceled_appointment,
    record_attendance_for_completed_appointment,
    record_attendance_for_rescheduled_appointment,
)
from scheduling.slots import (
    availability_capacity_for_slot,
    generate_available_slots,
    make_local_datetime,
    slot_capacity_snapshot,
    slot_is_available,
)


ACTIVE_APPOINTMENT_STATUSES = [Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED]


class AppointmentAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PATIENT,
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


class AgendaSettingsAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


class AgendaOperationalAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


def appointments_for_user(user):
    queryset = Appointment.objects.select_related("patient", "professional", "series")
    if user.is_superuser:
        return queryset

    profile = get_profile(user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT, UserProfile.Role.VIEWER}:
        return queryset
    if profile.is_patient and profile.patient_id:
        return queryset.filter(patient=profile.patient)
    if profile.is_professional and profile.professional_id:
        return queryset.filter(professional=profile.professional)
    return queryset.none()


def visible_patient_ids_for_user(user):
    if user.is_superuser:
        return Patient.objects.values_list("pk", flat=True)
    profile = get_profile(user)
    if not profile:
        return Patient.objects.none().values_list("pk", flat=True)
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT, UserProfile.Role.VIEWER}:
        return Patient.objects.values_list("pk", flat=True)
    if profile.is_patient and profile.patient_id:
        return Patient.objects.filter(pk=profile.patient_id).values_list("pk", flat=True)
    if profile.is_professional and profile.professional_id:
        return Patient.objects.filter(appointments__professional=profile.professional).distinct().values_list("pk", flat=True)
    return Patient.objects.none().values_list("pk", flat=True)


def profile_booking_source(profile):
    if not profile:
        return Appointment.BookingSource.ADMINISTRATION
    if profile.role == UserProfile.Role.PATIENT:
        return Appointment.BookingSource.PATIENT
    if profile.role == UserProfile.Role.PROFESSIONAL:
        return Appointment.BookingSource.PROFESSIONAL
    if profile.role == UserProfile.Role.MANAGEMENT:
        return Appointment.BookingSource.MANAGEMENT
    return Appointment.BookingSource.ADMINISTRATION


def user_can_manage_agenda(user):
    if user.is_superuser:
        return True
    profile = get_profile(user)
    return bool(
        profile
        and profile.role
        in {
            UserProfile.Role.PROFESSIONAL,
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
        }
    )


def add_model_validation_errors(form, error):
    if hasattr(error, "message_dict"):
        for field_messages in error.message_dict.values():
            for message in field_messages:
                form.add_error(None, message)
        return
    for message in error.messages:
        form.add_error(None, message)


def filter_appointment_search(queryset, query):
    if not query:
        return queryset
    return queryset.filter(
        Q(patient__full_name__icontains=query)
        | Q(professional__full_name__icontains=query)
        | Q(status__icontains=query)
        | Q(notes__icontains=query)
    )


def filter_availability_search(queryset, query):
    if not query:
        return queryset
    return queryset.filter(Q(professional__full_name__icontains=query) | Q(notes__icontains=query))


def calendar_week_start(request):
    selected = parse_date(request.GET.get("semana", "")) or timezone.localdate()
    return selected - timedelta(days=selected.weekday())


def agenda_redirect_for_date(day):
    week_start = day - timedelta(days=day.weekday())
    return redirect(f"{reverse('scheduling:appointments')}?semana={week_start.isoformat()}&dia={day.isoformat()}")


def escape_ics(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def format_ics_datetime(value):
    return value.astimezone(datetime_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def recurrence_dates_from_form(form):
    first_date = form.cleaned_data["appointment_date"]
    if form.cleaned_data.get("repeat_mode") != AppointmentSlotSearchForm.RepeatMode.WEEKLY:
        return [first_date]

    dates = [first_date]
    interval = form.cleaned_data.get("repeat_interval_weeks") or 1
    repeat_until = form.cleaned_data.get("repeat_until")
    repeat_count = form.cleaned_data.get("repeat_count")
    current = first_date

    while True:
        if repeat_count and len(dates) >= repeat_count:
            break
        current = current + timedelta(weeks=interval)
        if repeat_until and current > repeat_until:
            break
        dates.append(current)
        if not repeat_until and repeat_count and len(dates) >= repeat_count:
            break

    return dates


def create_series_for_dates(dates, form, user):
    if len(dates) <= 1:
        return None
    interval = form.cleaned_data.get("repeat_interval_weeks") or 1
    repeat_until = form.cleaned_data.get("repeat_until") or dates[-1]
    notes = f"Serie semanal criada a partir de {dates[0]:%d/%m/%Y}"
    return AppointmentSeries.objects.create(
        created_by=user,
        repeat_type=AppointmentSeries.RepeatType.WEEKLY,
        interval_weeks=interval,
        repeat_until=repeat_until,
        occurrences_count=len(dates),
        notes=notes,
    )


def has_future_series_appointments(appointment):
    if not appointment.series_id:
        return False
    return appointment.series.appointments.filter(
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        starts_at__gt=appointment.starts_at,
    ).exists()


def duplicate_appointments_exist(patient_ids, professional, starts_at, ends_at, exclude_ids=None):
    queryset = Appointment.objects.filter(
        patient_id__in=patient_ids,
        professional=professional,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    if exclude_ids:
        queryset = queryset.exclude(pk__in=exclude_ids)
    return queryset.exists()


def build_occurrence_payloads(
    *,
    professional,
    patient_ids,
    dates,
    selected_start,
    duration_minutes,
    requested_capacity,
    exclude_ids_by_date=None,
):
    payloads = []
    duration = timedelta(minutes=duration_minutes)
    requested_capacity = max(requested_capacity or 1, len(patient_ids))
    exclude_ids_by_date = exclude_ids_by_date or {}

    for current_date in dates:
        starts_at = make_local_datetime(current_date, selected_start)
        ends_at = starts_at + duration
        exclude_ids = exclude_ids_by_date.get(current_date.isoformat(), [])
        snapshot = slot_capacity_snapshot(
            professional.pk,
            starts_at,
            ends_at,
            exclude_appointment_ids=exclude_ids,
        )
        if snapshot["partial_overlap"]:
            raise ValidationError(f"{current_date:%d/%m/%Y}: o profissional ja possui atendimento nesse horario.")
        if not ProfessionalAvailability.objects.slot_available(
            professional_id=professional.pk,
            starts_at=starts_at,
            ends_at=ends_at,
        ):
            raise ValidationError(f"{current_date:%d/%m/%Y}: horario fora da disponibilidade recorrente.")
        if duplicate_appointments_exist(patient_ids, professional, starts_at, ends_at, exclude_ids=exclude_ids):
            raise ValidationError(f"{current_date:%d/%m/%Y}: ao menos um paciente ja possui este horario.")

        availability_capacity = availability_capacity_for_slot(professional, starts_at, ends_at)
        slot_capacity = max(snapshot["existing_capacity"], requested_capacity, availability_capacity)
        if snapshot["exact_count"] + len(patient_ids) > slot_capacity:
            raise ValidationError(f"{current_date:%d/%m/%Y}: capacidade da sessao excedida para este horario.")

        payloads.append(
            {
                "date": current_date,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "slot_capacity": slot_capacity,
                "slot_group": snapshot["slot_group"] or (uuid4().hex if slot_capacity > 1 else ""),
            }
        )

    return payloads


def build_calendar_session_groups(appointments):
    grouped = {}
    for appointment in appointments:
        if appointment.slot_capacity > 1:
            key = (
                appointment.professional_id,
                appointment.starts_at,
                appointment.ends_at,
                appointment.slot_group or f"slot-{appointment.starts_at.isoformat()}",
            )
        else:
            key = ("appointment", appointment.pk)
        grouped.setdefault(key, []).append(appointment)

    sessions = []
    for group_appointments in grouped.values():
        group_appointments = sorted(group_appointments, key=lambda item: item.patient.full_name)
        first = group_appointments[0]
        capacity = max(appointment.slot_capacity for appointment in group_appointments)
        occupied = len(group_appointments)
        requested = any(appointment.status == Appointment.Status.REQUESTED for appointment in group_appointments)
        completed = all(appointment.status == Appointment.Status.COMPLETED for appointment in group_appointments)
        status_class = Appointment.Status.REQUESTED if requested else Appointment.Status.COMPLETED if completed else first.status
        patient_names = [appointment.patient.full_name for appointment in group_appointments]
        preview_names = patient_names[:2]
        sessions.append(
            {
                "appointment": first,
                "appointments": group_appointments,
                "starts_at": first.starts_at,
                "ends_at": first.ends_at,
                "professional": first.professional,
                "status_class": status_class,
                "status_display": "Solicitado" if requested else "Realizado" if completed else first.get_status_display(),
                "is_group": capacity > 1,
                "is_recurring": any(appointment.series_id for appointment in group_appointments),
                "capacity": capacity,
                "occupied": occupied,
                "available": max(capacity - occupied, 0),
                "title": "Sessao em grupo" if capacity > 1 else first.patient.full_name,
                "patient_names": preview_names,
                "hidden_count": max(occupied - len(preview_names), 0),
            }
        )

    return sorted(sessions, key=lambda session: (session["starts_at"], session["professional"].full_name))


def annotate_credit_adjustment_flags(appointments):
    for appointment in appointments:
        appointment.needs_credit_adjustment = completion_needs_credit_adjustment(appointment)
    return appointments


class AppointmentListView(AppointmentAccessMixin, SearchableListView, ListView):
    model = Appointment
    template_name = "scheduling/appointment_list.html"
    context_object_name = "appointments"
    paginate_by = 12
    search_fields = ["patient__full_name", "professional__full_name", "status", "notes"]

    def get_queryset(self):
        queryset = appointments_for_user(self.request.user).order_by("starts_at")
        queryset = filter_appointment_search(queryset, self.request.GET.get("q", "").strip())
        selected_status = self.request.GET.get("status", "").strip()
        if selected_status in Appointment.Status.values:
            queryset = queryset.filter(status=selected_status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        annotate_credit_adjustment_flags(context["appointments"])
        week_start = calendar_week_start(self.request)
        week_end = week_start + timedelta(days=6)
        selected_day = parse_date(self.request.GET.get("dia", "")) or timezone.localdate()
        if selected_day < week_start or selected_day > week_end:
            selected_day = week_start
        week_days = [week_start + timedelta(days=offset) for offset in range(7)]
        hour_slots = range(6, 21)
        calendar_queryset = list(
            self.get_queryset()
            .filter(starts_at__date__gte=week_start, starts_at__date__lte=week_end)
            .exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED])
        )
        annotate_credit_adjustment_flags(calendar_queryset)
        events_by_day_hour = {day: {hour: [] for hour in hour_slots} for day in week_days}
        for appointment in calendar_queryset:
            local_start = timezone.localtime(appointment.starts_at)
            day = local_start.date()
            hour = local_start.hour
            if day in events_by_day_hour and hour in events_by_day_hour[day]:
                events_by_day_hour[day][hour].append(appointment)

        calendar_rows = []
        for hour in hour_slots:
            calendar_rows.append(
                {
                    "hour": hour,
                    "cells": [
                        {
                            "day": day,
                            "appointments": events_by_day_hour[day][hour],
                            "sessions": build_calendar_session_groups(events_by_day_hour[day][hour]),
                        }
                        for day in week_days
                    ],
                }
            )

        base_queryset = appointments_for_user(self.request.user)
        today = timezone.localdate()
        request_queue = base_queryset.filter(status=Appointment.Status.REQUESTED).order_by("starts_at")[:6]
        pending_reschedules = RescheduleRequest.objects.filter(status=RescheduleRequest.Status.PENDING)
        if not user_can_manage_agenda(self.request.user):
            profile = get_profile(self.request.user)
            if profile and profile.is_patient and profile.patient_id:
                pending_reschedules = pending_reschedules.filter(patient=profile.patient)
            else:
                pending_reschedules = pending_reschedules.none()
        pending_notifications = PatientNotification.objects.filter(status=PatientNotification.Status.PENDING)
        if not user_can_manage_agenda(self.request.user):
            profile = get_profile(self.request.user)
            if profile and profile.is_patient and profile.patient_id:
                pending_notifications = pending_notifications.filter(patient=profile.patient)
            else:
                pending_notifications = pending_notifications.none()

        context.update(
            {
                "status_choices": Appointment.Status.choices,
                "selected_status": self.request.GET.get("status", "").strip(),
                "week_start": week_start,
                "week_end": week_end,
                "previous_week": week_start - timedelta(days=7),
                "next_week": week_start + timedelta(days=7),
                "today": today,
                "selected_day": selected_day,
                "week_days": week_days,
                "calendar_rows": calendar_rows,
                "day_appointments": [
                    appointment
                    for appointment in calendar_queryset
                    if timezone.localtime(appointment.starts_at).date() == selected_day
                ],
                "today_total": base_queryset.filter(starts_at__date=today).exclude(
                    status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED]
                ).count(),
                "pending_total": base_queryset.filter(status=Appointment.Status.REQUESTED).count(),
                "group_total": base_queryset.filter(slot_capacity__gt=1).exclude(
                    status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED]
                ).count(),
                "recurring_total": base_queryset.filter(series__isnull=False).exclude(
                    status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED]
                ).count(),
                "absence_total": AppointmentAttendance.objects.filter(
                    appointment__in=base_queryset,
                    appointment__starts_at__date__gte=today.replace(day=1),
                    status__in=[
                        AppointmentAttendance.Status.ABSENT,
                        AppointmentAttendance.Status.JUSTIFIED_ABSENCE,
                    ],
                ).count(),
                "reschedule_request_total": pending_reschedules.count(),
                "notification_total": pending_notifications.count(),
                "request_queue": request_queue,
            }
        )
        return context


class AppointmentCalendarExportView(AppointmentAccessMixin, View):
    def get(self, request):
        appointments = appointments_for_user(request.user).order_by("starts_at")
        generated_at = datetime.now(datetime_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Lume Gestao//Agenda//PT-BR",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Lume Gestao - Agenda",
        ]
        for appointment in appointments:
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:lume-appointment-{appointment.pk}@lume.local",
                    f"DTSTAMP:{generated_at}",
                    f"DTSTART:{format_ics_datetime(appointment.starts_at)}",
                    f"DTEND:{format_ics_datetime(appointment.ends_at)}",
                    f"SUMMARY:{escape_ics(appointment.patient.full_name)} com {escape_ics(appointment.professional.full_name)}",
                    f"DESCRIPTION:{escape_ics(appointment.get_status_display())} - {escape_ics(appointment.notes)}",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        response = HttpResponse("\r\n".join(lines), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="lume-agenda.ics"'
        return response


class SlotSelectionMixin:
    template_name = "scheduling/slot_form.html"
    section_label = "Agenda"
    back_url_name = "scheduling:appointments"
    submit_label = "Ver horarios livres"
    slot_select_label = "Agendar neste horario"

    def get_context_data(self, form, slots=None, searched=False, booking_values=None):
        search_field_names = [
            name
            for name in [
                "patients",
                "service_plan",
                "professional",
                "appointment_date",
                "duration_minutes",
                "service_units",
                "session_capacity",
                "repeat_mode",
                "repeat_interval_weeks",
                "repeat_until",
                "repeat_count",
                "reschedule_scope",
            ]
            if name in form.fields
        ]
        return {
            "form": form,
            "search_fields": [form[name] for name in search_field_names],
            "slots": slots or [],
            "searched": searched,
            "booking_values": booking_values or {},
            "page_title": self.page_title,
            "section_label": self.section_label,
            "back_url": reverse(self.back_url_name),
            "submit_label": self.submit_label,
            "slot_select_label": self.slot_select_label,
        }

    def booking_values_from_form(self, form):
        values = {
            "professional": form.cleaned_data["professional"].pk,
            "appointment_date": form.cleaned_data["appointment_date"].isoformat(),
            "duration_minutes": form.cleaned_data["duration_minutes"],
            "notes": form.cleaned_data.get("notes", ""),
        }
        if "patients" in form.cleaned_data:
            values["patient_ids"] = [patient.pk for patient in form.cleaned_data["patients"]]
        if "service_plan" in form.cleaned_data and form.cleaned_data.get("service_plan"):
            values["service_plan"] = form.cleaned_data["service_plan"].pk
        if "service_units" in form.cleaned_data:
            values["service_units"] = form.cleaned_data["service_units"]
        if "session_capacity" in form.cleaned_data:
            values["session_capacity"] = form.cleaned_data["session_capacity"]
        if "repeat_mode" in form.cleaned_data:
            values["repeat_mode"] = form.cleaned_data["repeat_mode"]
            values["repeat_interval_weeks"] = form.cleaned_data.get("repeat_interval_weeks") or ""
            values["repeat_until"] = form.cleaned_data.get("repeat_until").isoformat() if form.cleaned_data.get("repeat_until") else ""
            values["repeat_count"] = form.cleaned_data.get("repeat_count") or ""
        if "reschedule_scope" in form.cleaned_data:
            values["reschedule_scope"] = form.cleaned_data["reschedule_scope"]
        return values

    def render_slot_page(self, form, slots=None, searched=False, booking_values=None):
        return render(
            self.request,
            self.template_name,
            self.get_context_data(
                form=form,
                slots=slots,
                searched=searched,
                booking_values=booking_values,
            ),
        )

    def get_slots(self, form):
        slots = generate_available_slots(
            professional=form.cleaned_data["professional"],
            day=form.cleaned_data["appointment_date"],
            duration_minutes=form.cleaned_data["duration_minutes"],
            exclude_appointment=getattr(self, "original_appointment", None),
        )
        original = getattr(self, "original_appointment", None)
        if original and form.cleaned_data["professional"].pk == original.professional_id:
            slots = [
                slot
                for slot in slots
                if not (slot["starts_at"] == original.starts_at and slot["ends_at"] == original.ends_at)
            ]
        return slots

    def selected_interval_from_form(self, form):
        selected_start = form.cleaned_data.get("selected_start")
        if not selected_start:
            form.add_error(None, "Selecione um dos horarios livres antes de confirmar.")
            return None, None

        starts_at = make_local_datetime(form.cleaned_data["appointment_date"], selected_start)
        ends_at = starts_at + timedelta(minutes=form.cleaned_data["duration_minutes"])
        exclude_appointment = getattr(self, "original_appointment", None)
        if not slot_is_available(form.cleaned_data["professional"], starts_at, ends_at, exclude_appointment):
            snapshot = slot_capacity_snapshot(
                form.cleaned_data["professional"].pk,
                starts_at,
                ends_at,
                exclude_appointment_id=getattr(exclude_appointment, "pk", None),
            )
            if snapshot["existing_capacity"] and snapshot["remaining_capacity"] <= 0:
                form.add_error(None, "Esta sessao ja atingiu a capacidade maxima. Escolha outro horario livre.")
            else:
                form.add_error(None, "Este horario acabou de ficar indisponivel. Escolha outro horario livre.")
            return None, None
        return starts_at, ends_at


class AppointmentCreateView(SlotSelectionMixin, AppointmentAccessMixin, View):
    form_class = AppointmentSlotSearchForm
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Agendamento"
    slot_select_label = "Agendar neste horario"

    def get_form(self, data=None):
        return self.form_class(data=data, request=self.request)

    def get(self, request, *args, **kwargs):
        form = self.get_form(request.GET or None)
        slots = []
        booking_values = {}
        searched = form.is_bound
        if form.is_bound and form.is_valid():
            slots = self.get_slots(form)
            booking_values = self.booking_values_from_form(form)
        return self.render_slot_page(form, slots=slots, searched=searched, booking_values=booking_values)

    def post(self, request, *args, **kwargs):
        form = self.get_form(request.POST)
        slots = []
        booking_values = {}
        if form.is_valid():
            slots = self.get_slots(form)
            booking_values = self.booking_values_from_form(form)
            starts_at, ends_at = self.selected_interval_from_form(form)
            if starts_at and ends_at:
                profile = get_profile(request.user)
                patients = list(form.cleaned_data["patients"])
                recurrence_dates = recurrence_dates_from_form(form)
                try:
                    occurrence_payloads = build_occurrence_payloads(
                        professional=form.cleaned_data["professional"],
                        patient_ids=[patient.pk for patient in patients],
                        dates=recurrence_dates,
                        selected_start=timezone.localtime(starts_at).time(),
                        duration_minutes=form.cleaned_data["duration_minutes"],
                        requested_capacity=form.cleaned_data["session_capacity"],
                    )
                except ValidationError as error:
                    add_model_validation_errors(form, error)
                    return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)

                status = Appointment.Status.REQUESTED if profile and profile.is_patient else Appointment.Status.SCHEDULED
                with transaction.atomic():
                    series = create_series_for_dates(recurrence_dates, form, request.user)
                    created_count = 0
                    for payload in occurrence_payloads:
                        slot_group = payload["slot_group"]
                        for patient in patients:
                            appointment = Appointment(
                                patient=patient,
                                professional=form.cleaned_data["professional"],
                                service_plan=form.cleaned_data.get("service_plan"),
                                starts_at=payload["starts_at"],
                                ends_at=payload["ends_at"],
                                status=status,
                                booking_source=profile_booking_source(profile),
                                booked_by=request.user,
                                series=series,
                                slot_group=slot_group,
                                slot_capacity=payload["slot_capacity"],
                                service_units=form.cleaned_data["service_units"],
                                notes=form.cleaned_data.get("notes", ""),
                            )
                            try:
                                appointment.full_clean()
                                appointment.save()
                            except ValidationError as error:
                                add_model_validation_errors(form, error)
                                transaction.set_rollback(True)
                                return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)
                            created_count += 1
                    first_created_day = timezone.localtime(occurrence_payloads[0]["starts_at"]).date()

                if len(recurrence_dates) > 1:
                    messages.success(
                        request,
                        f"Serie criada com sucesso. Foram gerados {created_count} agendamento(s).",
                    )
                else:
                    messages.success(request, "Agendamento cadastrado com sucesso.")
                return agenda_redirect_for_date(first_created_day)

        return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)


class AppointmentConfirmView(AppointmentAccessMixin, View):
    def post(self, request, pk):
        profile = get_profile(request.user)
        if not request.user.is_superuser and (not profile or profile.role not in {UserProfile.Role.PROFESSIONAL, UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}):
            messages.error(request, "Seu perfil nao pode confirmar agendamentos.")
            return redirect("scheduling:appointments")

        appointment = get_object_or_404(appointments_for_user(request.user), pk=pk)
        if appointment.status != Appointment.Status.REQUESTED:
            messages.warning(request, "Este agendamento nao esta aguardando confirmacao.")
            return redirect("scheduling:appointments")

        appointment.status = Appointment.Status.SCHEDULED
        appointment.full_clean()
        appointment.save(update_fields=["status", "updated_at", "slot_group", "slot_capacity"])
        messages.success(request, "Agendamento confirmado com sucesso.")
        return redirect("scheduling:appointments")


class AppointmentUpdateView(FormContextMixin, AppointmentAccessMixin, UpdateView):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]
    model = Appointment
    form_class = AppointmentForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Agendamento"
    section_label = "Agenda"
    back_url_name = "scheduling:appointments"

    def get_queryset(self):
        return appointments_for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        if form.instance.status == Appointment.Status.COMPLETED:
            form.instance.completed_by = self.request.user
            form.instance.completed_at = form.instance.completed_at or timezone.now()
        messages.success(self.request, "Agendamento atualizado com sucesso.")
        return super().form_valid(form)


class AppointmentCancelView(AppointmentAccessMixin, View):
    def post(self, request, pk):
        appointment = get_object_or_404(appointments_for_user(request.user), pk=pk)
        if appointment.status == Appointment.Status.COMPLETED:
            messages.error(request, "Atendimento realizado nao pode ser cancelado.")
            return redirect("scheduling:appointments")
        if hasattr(appointment, "service_usage"):
            messages.error(request, "Atendimento ja baixado nao pode ser cancelado.")
            return redirect("scheduling:appointments")

        appointment.status = Appointment.Status.CANCELED
        appointment.full_clean()
        appointment.save(update_fields=["status", "updated_at"])
        record_attendance_for_canceled_appointment(appointment, user=request.user)
        messages.success(request, "Agendamento cancelado sem consumo de credito.")
        return redirect("scheduling:appointments")


class AppointmentRescheduleView(SlotSelectionMixin, AppointmentAccessMixin, FormView):
    form_class = AppointmentRescheduleSlotForm
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Reagendamento"
    submit_label = "Ver novos horarios"
    slot_select_label = "Reagendar para este horario"

    def dispatch(self, request, *args, **kwargs):
        self.original_appointment = get_object_or_404(appointments_for_user(request.user), pk=kwargs["pk"])
        if self.original_appointment.status in {
            Appointment.Status.COMPLETED,
            Appointment.Status.CANCELED,
            Appointment.Status.RESCHEDULED,
        } or hasattr(self.original_appointment, "service_usage"):
            messages.error(request, "Este agendamento nao pode ser reagendado.")
            return redirect("scheduling:appointments")
        profile = get_profile(request.user)
        if profile and profile.is_patient:
            settings = ClinicSettings.load()
            deadline = timezone.now() + timedelta(hours=settings.rescheduling_deadline_hours)
            if self.original_appointment.starts_at <= deadline:
                messages.error(
                    request,
                    f"Reagendamentos pelo paciente precisam ser solicitados com pelo menos "
                    f"{settings.rescheduling_deadline_hours} horas de antecedencia.",
                )
                return redirect("scheduling:appointments")
        self.has_future_series = has_future_series_appointments(self.original_appointment)
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, data=None):
        return self.form_class(
            data=data,
            request=self.request,
            original_appointment=self.original_appointment,
            has_future_series=self.has_future_series,
        )

    def get(self, request, *args, **kwargs):
        form = self.get_form(request.GET or None)
        slots = []
        booking_values = {}
        searched = form.is_bound
        if form.is_bound and form.is_valid():
            slots = self.get_slots(form)
            booking_values = self.booking_values_from_form(form)
        return self.render_slot_page(form, slots=slots, searched=searched, booking_values=booking_values)

    def post(self, request, *args, **kwargs):
        form = self.get_form(request.POST)
        slots = []
        booking_values = {}
        if not form.is_valid():
            return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)

        slots = self.get_slots(form)
        booking_values = self.booking_values_from_form(form)
        starts_at, ends_at = self.selected_interval_from_form(form)
        if not starts_at or not ends_at:
            return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)
        if (
            form.cleaned_data["professional"].pk == self.original_appointment.professional_id
            and starts_at == self.original_appointment.starts_at
            and ends_at == self.original_appointment.ends_at
        ):
            form.add_error(None, "Escolha um horario diferente do agendamento atual.")
            return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)

        scope = form.cleaned_data.get("reschedule_scope", AppointmentRescheduleSlotForm.Scope.CURRENT)
        profile = get_profile(request.user)
        new_status = Appointment.Status.REQUESTED if profile and profile.is_patient else Appointment.Status.SCHEDULED

        if scope == AppointmentRescheduleSlotForm.Scope.CURRENT_AND_FUTURE and self.original_appointment.series_id:
            return self.reschedule_current_and_future(form, starts_at, ends_at, new_status, slots, booking_values)
        return self.reschedule_current_only(form, starts_at, ends_at, new_status, slots, booking_values)

    def reschedule_current_only(self, form, starts_at, ends_at, new_status, slots, booking_values):
        profile = get_profile(self.request.user)
        try:
            with transaction.atomic():
                original = Appointment.objects.select_for_update().get(pk=self.original_appointment.pk)
                original.status = Appointment.Status.RESCHEDULED
                original.full_clean()
                original.save(update_fields=["status", "updated_at"])
                record_attendance_for_rescheduled_appointment(original, user=self.request.user)
                target_day = timezone.localtime(starts_at).date()
                payload = build_occurrence_payloads(
                    professional=form.cleaned_data["professional"],
                    patient_ids=[original.patient_id],
                    dates=[target_day],
                    selected_start=timezone.localtime(starts_at).time(),
                    duration_minutes=form.cleaned_data["duration_minutes"],
                    requested_capacity=original.slot_capacity,
                    exclude_ids_by_date={target_day.isoformat(): [original.pk]},
                )[0]
                new_appointment = Appointment(
                    patient=original.patient,
                    professional=form.cleaned_data["professional"],
                    service_plan=original.service_plan,
                    starts_at=payload["starts_at"],
                    ends_at=payload["ends_at"],
                    status=new_status,
                    booking_source=profile_booking_source(profile),
                    booked_by=self.request.user,
                    rescheduled_from=original,
                    series=original.series,
                    slot_group=payload["slot_group"],
                    slot_capacity=payload["slot_capacity"],
                    service_units=original.service_units,
                    notes=form.cleaned_data.get("notes", ""),
                )
                new_appointment.full_clean()
                new_appointment.save()
        except ValidationError as error:
            add_model_validation_errors(form, error)
            return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)

        messages.success(self.request, "Agendamento reagendado sem consumo de credito.")
        return agenda_redirect_for_date(timezone.localtime(new_appointment.starts_at).date())

    def reschedule_current_and_future(self, form, starts_at, ends_at, new_status, slots, booking_values):
        profile = get_profile(self.request.user)
        delta = starts_at - self.original_appointment.starts_at
        first_replacement_day = None
        try:
            with transaction.atomic():
                sources = list(
                    self.original_appointment.series.appointments.select_for_update()
                    .filter(
                        status__in=ACTIVE_APPOINTMENT_STATUSES,
                        starts_at__gte=self.original_appointment.starts_at,
                    )
                    .order_by("starts_at")
                )
                if not sources:
                    messages.error(self.request, "Nao ha sessoes futuras disponiveis para reagendar.")
                    return redirect(self.success_url)

                occurrences = []
                for source in sources:
                    shifted_start = source.starts_at + delta
                    occurrences.append(
                        {
                            "source": source,
                            "date": timezone.localtime(shifted_start).date(),
                            "starts_at": shifted_start,
                            "ends_at": source.ends_at + delta,
                        }
                    )

                grouped_occurrences = {}
                for item in occurrences:
                    grouped_occurrences.setdefault(item["date"], []).append(item)

                payload_by_date = {}
                for current_date, items in grouped_occurrences.items():
                    patient_ids = [item["source"].patient_id for item in items]
                    exclude_ids_by_date = {current_date.isoformat(): [item["source"].pk for item in items]}
                    payload = build_occurrence_payloads(
                        professional=form.cleaned_data["professional"],
                        patient_ids=patient_ids,
                        dates=[current_date],
                        selected_start=timezone.localtime(items[0]["starts_at"]).time(),
                        duration_minutes=form.cleaned_data["duration_minutes"],
                        requested_capacity=max(item["source"].slot_capacity for item in items),
                        exclude_ids_by_date=exclude_ids_by_date,
                    )[0]
                    payload_by_date[current_date] = payload

                new_series = AppointmentSeries.objects.create(
                    created_by=self.request.user,
                    repeat_type=AppointmentSeries.RepeatType.WEEKLY,
                    interval_weeks=self.original_appointment.series.interval_weeks,
                    repeat_until=max(payload_by_date) if payload_by_date else None,
                    occurrences_count=len(payload_by_date),
                    notes=f"Serie ajustada a partir de {timezone.localtime(starts_at):%d/%m/%Y}",
                )
                for source in sources:
                    source.status = Appointment.Status.RESCHEDULED
                    source.full_clean()
                    source.save(update_fields=["status", "updated_at"])
                    record_attendance_for_rescheduled_appointment(source, user=self.request.user)
                    shifted_date = timezone.localtime(source.starts_at + delta).date()
                    payload = payload_by_date[shifted_date]
                    replacement = Appointment(
                        patient=source.patient,
                        professional=form.cleaned_data["professional"],
                        service_plan=source.service_plan,
                        starts_at=source.starts_at + delta,
                        ends_at=source.ends_at + delta,
                        status=new_status,
                        booking_source=profile_booking_source(profile),
                        booked_by=self.request.user,
                        rescheduled_from=source,
                        series=new_series,
                        slot_group=payload["slot_group"],
                        slot_capacity=payload["slot_capacity"],
                        service_units=source.service_units,
                        notes=form.cleaned_data.get("notes", "") or source.notes,
                    )
                    replacement.full_clean()
                    replacement.save()
                    first_replacement_day = first_replacement_day or timezone.localtime(replacement.starts_at).date()
        except ValidationError as error:
            add_model_validation_errors(form, error)
            return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)

        messages.success(self.request, "Sessao atual e proximas reagendadas com sucesso.")
        return agenda_redirect_for_date(first_replacement_day or timezone.localdate())


class AppointmentCompleteView(AppointmentAccessMixin, View):
    def post(self, request, pk):
        with transaction.atomic():
            allowed_appointment_ids = appointments_for_user(request.user).filter(pk=pk).values("pk")
            appointment = get_object_or_404(
                Appointment.objects.select_related("patient", "professional").select_for_update(),
                pk__in=allowed_appointment_ids,
            )
            if appointment.status in {Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED}:
                messages.error(request, "Agendamentos cancelados ou reagendados nao consomem credito.")
                return redirect("scheduling:appointments")
            if hasattr(appointment, "service_usage"):
                messages.error(request, "Este atendimento ja foi baixado.")
                return redirect("scheduling:appointments")

            try:
                package = completion_package_for_appointment(appointment, lock=True)
            except ValidationError as error:
                messages.error(request, error.messages[0])
                return redirect("scheduling:appointments")
            needs_credit = not package or package.remaining_sessions < appointment.service_units
            if needs_credit:
                if request.POST.get("add_credit") != "1":
                    messages.error(
                        request,
                        "O cliente nao tem creditos disponiveis. Confirme no botao de baixa para adicionar 1 credito e continuar.",
                    )
                    return redirect("scheduling:appointments")
                try:
                    package = ensure_credit_for_appointment(appointment, request.user)
                except ValidationError as error:
                    messages.error(request, error.messages[0])
                    return redirect("scheduling:appointments")
            appointment.status = Appointment.Status.COMPLETED
            appointment.completed_by = request.user
            appointment.completed_at = timezone.now()
            appointment.full_clean()
            appointment.save()
            ServiceUsage.objects.create(
                service_package=package,
                appointment=appointment,
                units=appointment.service_units,
                registered_by=request.user,
            )
            record_attendance_for_completed_appointment(appointment, user=request.user)
            package.used_sessions += appointment.service_units
            if package.used_sessions >= package.total_sessions:
                package.status = ServicePackage.Status.FINISHED
            package.full_clean()
            package.save()

        messages.success(request, "Atendimento baixado e adesao atualizada.")
        return redirect("scheduling:appointments")


class AppointmentAbsenceView(AgendaOperationalAccessMixin, View):
    def post(self, request, pk):
        appointment = get_object_or_404(appointments_for_user(request.user), pk=pk)
        form = AppointmentAttendanceForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Nao foi possivel registrar a falta.")
            return redirect("scheduling:appointments")
        justified = form.cleaned_data["status"] == AppointmentAttendance.Status.JUSTIFIED_ABSENCE
        try:
            mark_absence(appointment, user=request.user, justified=justified, notes=form.cleaned_data.get("notes", ""))
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return redirect("scheduling:appointments")
        messages.success(request, "Falta registrada sem consumo de credito.")
        return redirect("scheduling:appointments")


class RescheduleRequestCreateView(FormContextMixin, AppointmentAccessMixin, CreateView):
    model = RescheduleRequest
    form_class = RescheduleRequestForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Solicitar remarcacao"
    section_label = "Agenda"
    submit_label = "Enviar solicitacao"
    back_url_name = "scheduling:appointments"

    def dispatch(self, request, *args, **kwargs):
        self.appointment = get_object_or_404(appointments_for_user(request.user), pk=kwargs["pk"])
        if self.appointment.status in {
            Appointment.Status.COMPLETED,
            Appointment.Status.CANCELED,
            Appointment.Status.RESCHEDULED,
        }:
            messages.error(request, "Este agendamento nao pode receber solicitacao de remarcacao.")
            return redirect("scheduling:appointments")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.appointment = self.appointment
        form.instance.patient = self.appointment.patient
        form.instance.requested_by = self.request.user
        messages.success(self.request, "Solicitacao de remarcacao registrada para a equipe.")
        return super().form_valid(form)


class RescheduleRequestListView(AgendaOperationalAccessMixin, SearchableListView, ListView):
    model = RescheduleRequest
    template_name = "scheduling/reschedule_request_list.html"
    context_object_name = "requests"
    paginate_by = 20
    search_fields = ["patient__full_name", "reason", "decision_note"]

    def get_queryset(self):
        queryset = RescheduleRequest.objects.select_related("patient", "appointment", "requested_by", "decided_by")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(patient__full_name__icontains=query)
                | Q(reason__icontains=query)
                | Q(decision_note__icontains=query)
            )
        selected_status = self.request.GET.get("status", "").strip()
        if selected_status in RescheduleRequest.Status.values:
            queryset = queryset.filter(status=selected_status)
        return queryset.order_by("status", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = RescheduleRequest.Status.choices
        context["selected_status"] = self.request.GET.get("status", "").strip()
        return context


class RescheduleRequestDecisionView(AgendaOperationalAccessMixin, View):
    allowed_actions = {
        "aprovar": RescheduleRequest.Status.APPROVED,
        "recusar": RescheduleRequest.Status.DECLINED,
        "cancelar": RescheduleRequest.Status.CANCELED,
    }

    def post(self, request, pk, action):
        reschedule_request = get_object_or_404(RescheduleRequest, pk=pk)
        status = self.allowed_actions.get(action)
        if not status:
            messages.error(request, "Acao de remarcacao invalida.")
            return redirect("scheduling:reschedule_requests")
        reschedule_request.status = status
        reschedule_request.decided_by = request.user
        reschedule_request.decided_at = timezone.now()
        reschedule_request.decision_note = request.POST.get("decision_note", "").strip()
        reschedule_request.full_clean()
        reschedule_request.save()
        if status == RescheduleRequest.Status.APPROVED:
            messages.success(request, "Solicitacao aprovada. Escolha o novo horario para concluir.")
            return redirect("scheduling:appointment_reschedule", pk=reschedule_request.appointment_id)
        messages.success(request, "Solicitacao atualizada.")
        return redirect("scheduling:reschedule_requests")


class PatientProgressView(AppointmentAccessMixin, View):
    template_name = "scheduling/patient_progress.html"

    def get(self, request, patient_pk):
        patient = get_object_or_404(Patient.objects.filter(pk__in=visible_patient_ids_for_user(request.user)), pk=patient_pk)
        context = {
            "patient": patient,
            "summary": patient_monthly_summary(patient),
            "goals": PatientGoal.objects.filter(patient=patient).order_by("status", "-created_at"),
            "checkins": PatientCheckIn.objects.filter(patient=patient).select_related("appointment").order_by("-created_at")[:12],
            "attendance": AppointmentAttendance.objects.filter(patient=patient).select_related("appointment").order_by("-appointment__starts_at")[:20],
            "notifications": PatientNotification.objects.filter(patient=patient).order_by("-due_at")[:12],
        }
        return render(request, self.template_name, context)


class PatientCheckInCreateView(FormContextMixin, AppointmentAccessMixin, CreateView):
    model = PatientCheckIn
    form_class = PatientCheckInForm
    template_name = "core/form.html"
    page_title = "Check-in de progresso"
    section_label = "Agenda"
    submit_label = "Salvar check-in"
    back_url_name = "scheduling:appointments"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient.objects.filter(pk__in=visible_patient_ids_for_user(request.user)), pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["patient"] = self.patient
        return kwargs

    def form_valid(self, form):
        form.instance.patient = self.patient
        form.instance.created_by = self.request.user
        messages.success(self.request, "Check-in registrado.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("scheduling:patient_progress", kwargs={"patient_pk": self.patient.pk})


class PatientGoalCreateView(FormContextMixin, AppointmentAccessMixin, CreateView):
    model = PatientGoal
    form_class = PatientGoalForm
    template_name = "core/form.html"
    page_title = "Nova meta do paciente"
    section_label = "Agenda"
    submit_label = "Salvar meta"
    back_url_name = "scheduling:appointments"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient.objects.filter(pk__in=visible_patient_ids_for_user(request.user)), pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.patient = self.patient
        form.instance.created_by = self.request.user
        messages.success(self.request, "Meta registrada.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("scheduling:patient_progress", kwargs={"patient_pk": self.patient.pk})


class NotificationCenterView(AppointmentAccessMixin, SearchableListView, ListView):
    model = PatientNotification
    template_name = "scheduling/notification_center.html"
    context_object_name = "notifications"
    paginate_by = 20
    search_fields = ["patient__full_name", "message", "error_message"]

    def get_queryset(self):
        queryset = PatientNotification.objects.select_related("patient", "appointment").order_by("status", "due_at")
        if not user_can_manage_agenda(self.request.user):
            profile = get_profile(self.request.user)
            if profile and profile.is_patient and profile.patient_id:
                queryset = queryset.filter(patient=profile.patient)
            else:
                queryset = queryset.none()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(patient__full_name__icontains=query) | Q(message__icontains=query))
        selected_status = self.request.GET.get("status", "").strip()
        if selected_status in PatientNotification.Status.values:
            queryset = queryset.filter(status=selected_status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = PatientNotification.Status.choices
        context["selected_status"] = self.request.GET.get("status", "").strip()
        return context


class GenerateNotificationsView(AgendaOperationalAccessMixin, View):
    def post(self, request):
        created = generate_operational_notifications()
        total = sum(created.values())
        messages.success(request, f"Central atualizada com {total} novo(s) aviso(s).")
        return redirect("scheduling:notifications")


def availabilities_for_user(user):
    queryset = ProfessionalAvailability.objects.select_related("professional")
    if user.is_superuser:
        return queryset
    profile = get_profile(user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT, UserProfile.Role.VIEWER}:
        return queryset
    if profile.is_professional and profile.professional_id:
        return queryset.filter(professional=profile.professional)
    return queryset.none()


class ProfessionalAvailabilityAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


class ProfessionalAvailabilityListView(ProfessionalAvailabilityAccessMixin, SearchableListView, ListView):
    model = ProfessionalAvailability
    template_name = "scheduling/availability_list.html"
    context_object_name = "availabilities"
    paginate_by = 12
    search_fields = ["professional__full_name", "notes"]

    def get_queryset(self):
        return filter_availability_search(availabilities_for_user(self.request.user), self.request.GET.get("q", "").strip())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        availabilities = list(self.get_queryset())
        grouped = {}
        for availability in availabilities:
            professional = availability.professional
            grouped.setdefault(
                professional.pk,
                {
                    "professional": professional,
                    "days": {weekday: [] for weekday, _label in ProfessionalAvailability.Weekday.choices},
                    "total": 0,
                    "active": 0,
                },
            )
            grouped[professional.pk]["days"][availability.weekday].append(availability)
            grouped[professional.pk]["total"] += 1
            if availability.active:
                grouped[professional.pk]["active"] += 1

        context["weekday_choices"] = ProfessionalAvailability.Weekday.choices
        availability_boards = []
        for board in grouped.values():
            board["weekdays"] = [
                {"value": weekday, "label": label, "items": board["days"][weekday]}
                for weekday, label in ProfessionalAvailability.Weekday.choices
            ]
            availability_boards.append(board)
        context["availability_boards"] = sorted(
            availability_boards,
            key=lambda item: item["professional"].full_name,
        )
        return context


class ProfessionalAvailabilityCreateView(ProfessionalAvailabilityAccessMixin, FormView):
    form_class = ProfessionalAvailabilityBatchForm
    template_name = "scheduling/availability_form.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        created_count = 0
        updated_count = 0
        with transaction.atomic():
            for weekday in form.cleaned_data["weekdays"]:
                for starts_at, ends_at in form.cleaned_data["time_windows"]:
                    _availability, created = ProfessionalAvailability.objects.update_or_create(
                        professional=form.cleaned_data["professional"],
                        weekday=weekday,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        valid_from=form.cleaned_data["valid_from"],
                        defaults={
                            "valid_until": form.cleaned_data["valid_until"],
                            "session_capacity": form.cleaned_data["session_capacity"],
                            "active": form.cleaned_data["active"],
                            "notes": form.cleaned_data.get("notes", ""),
                        },
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
        message = f"{created_count} disponibilidade(s) criada(s)"
        if updated_count:
            message += f" e {updated_count} atualizada(s)"
        messages.success(self.request, f"{message} com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": self.page_title,
                "section_label": self.section_label,
                "back_url": reverse(self.back_url_name),
            }
        )
        return context


class ProfessionalAvailabilityUpdateView(FormContextMixin, ProfessionalAvailabilityAccessMixin, UpdateView):
    model = ProfessionalAvailability
    form_class = ProfessionalAvailabilityForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"

    def get_queryset(self):
        return availabilities_for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Disponibilidade atualizada com sucesso.")
        return super().form_valid(form)


class ProfessionalAvailabilityDeleteView(DeletionDecisionMixin, FormContextMixin, ProfessionalAvailabilityAccessMixin, DeleteView):
    model = ProfessionalAvailability
    default_delete_action = DELETE_ACTION_NOW
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Excluir disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"
    entity_label = "disponibilidade"

    def get_queryset(self):
        return availabilities_for_user(self.request.user)

    def perform_delete_now(self):
        hard_delete_availability(self.object)

    def perform_deactivate(self):
        mark_active_object_for_deletion(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        availability = self.object
        context.update(
            {
                "object_name": (
                    f"{availability.professional.full_name} - {availability.get_weekday_display()} "
                    f"{availability.starts_at:%H:%M} ate {availability.ends_at:%H:%M}"
                ),
                "entity_label": "disponibilidade",
                "delete_explanation": (
                    "Escolha se deseja apenas retirar esta regra da agenda ativa ou remover definitivamente."
                ),
            }
        )
        return context


class AgendaSettingsUpdateView(FormContextMixin, AgendaSettingsAccessMixin, UpdateView):
    model = ClinicSettings
    form_class = AgendaSettingsForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Configuracoes da agenda"
    section_label = "Agenda"
    back_url_name = "scheduling:appointments"

    def get_object(self, queryset=None):
        return ClinicSettings.load()

    def form_valid(self, form):
        messages.success(self.request, "Configuracoes da agenda atualizadas com sucesso.")
        return super().form_valid(form)


class ServicePackageListView(FinanceAccessMixin, SearchableListView, ListView):
    model = ServicePackage
    template_name = "scheduling/package_list.html"
    context_object_name = "packages"
    paginate_by = 12
    search_fields = ["membership__patient__full_name", "membership__plan__name", "status"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("membership__patient", "membership__plan")
            .exclude(status=ServicePackage.Status.CANCELED)
        )


class ServicePackageAdjustmentListView(FinanceAccessMixin, SearchableListView, ListView):
    model = ServicePackageAdjustment
    template_name = "scheduling/package_adjustment_list.html"
    context_object_name = "adjustments"
    paginate_by = 20
    search_fields = [
        "service_package__membership__patient__full_name",
        "service_package__membership__plan__name",
        "reason",
        "notes",
    ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "service_package__membership__patient",
                "service_package__membership__plan",
                "appointment",
                "created_by",
            )
        )


class ServicePackageCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = ServicePackage
    form_class = ServicePackageForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Adesao"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"

    def get_initial(self):
        initial = super().get_initial()
        patient_id = self.request.GET.get("patient")
        plan_id = self.request.GET.get("plan")
        if patient_id:
            initial["patient"] = patient_id
        if plan_id:
            initial["plan"] = plan_id
        return initial

    def form_valid(self, form):
        patient = form.cleaned_data["patient"]
        plan = form.cleaned_data["plan"]
        messages.success(self.request, f"Adesao criada para {patient.full_name} em {plan.name}.")
        return super().form_valid(form)


class ServicePackageUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = ServicePackage
    form_class = ServicePackageForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Adesao"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"

    def form_valid(self, form):
        patient = form.cleaned_data["patient"]
        plan = form.cleaned_data["plan"]
        messages.success(self.request, f"Adesao atualizada para {patient.full_name} em {plan.name}.")
        return super().form_valid(form)


class ServicePackageDeleteView(DeletionDecisionMixin, FormContextMixin, FinanceAccessMixin, DeleteView):
    model = ServicePackage
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Excluir adesao"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"
    entity_label = "adesao"

    def perform_delete_now(self):
        hard_delete_service_package(self.object)

    def perform_deactivate(self):
        mark_package_for_deletion(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        package = self.object
        context.update(
            {
                "object_name": f"{package.membership.patient.full_name} - {package.membership.plan.name}",
                "entity_label": "adesao",
                "delete_explanation": (
                    "Escolha se deseja inativar esta adesao ou remover definitivamente seus registros."
                ),
            }
        )
        return context
