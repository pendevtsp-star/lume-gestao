from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone as datetime_timezone

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
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
from django.views.generic import CreateView, FormView, ListView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import FinanceAccessMixin, RoleRequiredMixin, get_profile
from core.views import FormContextMixin, SearchableListView
from scheduling.forms import (
    AppointmentForm,
    AppointmentRescheduleSlotForm,
    AppointmentSlotSearchForm,
    ProfessionalAvailabilityForm,
    ServicePackageForm,
)
from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage, ServiceUsage
from scheduling.slots import generate_available_slots, make_local_datetime, slot_is_available


class AppointmentAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.PATIENT,
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]


def appointments_for_user(user):
    queryset = Appointment.objects.select_related("patient", "professional")
    if user.is_superuser:
        return queryset

    profile = get_profile(user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_patient and profile.patient_id:
        return queryset.filter(patient=profile.patient)
    if profile.is_professional and profile.professional_id:
        return queryset.filter(professional=profile.professional)
    return queryset.none()


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
    )


def calendar_week_start(request):
    selected = parse_date(request.GET.get("semana", "")) or timezone.localdate()
    return selected - timedelta(days=selected.weekday())


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


class AppointmentListView(AppointmentAccessMixin, SearchableListView, ListView):
    model = Appointment
    template_name = "scheduling/appointment_list.html"
    context_object_name = "appointments"
    paginate_by = 12
    search_fields = ["patient__full_name", "professional__full_name", "status"]

    def get_queryset(self):
        queryset = appointments_for_user(self.request.user).order_by("starts_at")
        return filter_appointment_search(queryset, self.request.GET.get("q", "").strip())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        week_start = calendar_week_start(self.request)
        week_end = week_start + timedelta(days=6)
        selected_day = parse_date(self.request.GET.get("dia", "")) or timezone.localdate()
        if selected_day < week_start or selected_day > week_end:
            selected_day = week_start
        week_days = [week_start + timedelta(days=offset) for offset in range(7)]
        hour_slots = range(6, 21)
        calendar_queryset = (
            self.get_queryset()
            .filter(starts_at__date__gte=week_start, starts_at__date__lte=week_end)
            .exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED])
        )
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
                        }
                        for day in week_days
                    ],
                }
            )

        context.update(
            {
                "week_start": week_start,
                "week_end": week_end,
                "previous_week": week_start - timedelta(days=7),
                "next_week": week_start + timedelta(days=7),
                "today": timezone.localdate(),
                "selected_day": selected_day,
                "week_days": week_days,
                "calendar_rows": calendar_rows,
                "day_appointments": calendar_queryset.filter(starts_at__date=selected_day).order_by("starts_at"),
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
            for name in ["patient", "professional", "appointment_date", "duration_minutes", "service_units"]
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
        if "patient" in form.cleaned_data:
            values["patient"] = form.cleaned_data["patient"].pk
        if "service_units" in form.cleaned_data:
            values["service_units"] = form.cleaned_data["service_units"]
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
                status = Appointment.Status.REQUESTED if profile and profile.is_patient else Appointment.Status.SCHEDULED
                appointment = Appointment(
                    patient=form.cleaned_data["patient"],
                    professional=form.cleaned_data["professional"],
                    starts_at=starts_at,
                    ends_at=ends_at,
                    status=status,
                    booking_source=profile_booking_source(profile),
                    booked_by=request.user,
                    service_units=form.cleaned_data["service_units"],
                    notes=form.cleaned_data.get("notes", ""),
                )
                try:
                    appointment.full_clean()
                    appointment.save()
                except ValidationError as error:
                    add_model_validation_errors(form, error)
                    return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)
                messages.success(request, "Agendamento cadastrado com sucesso.")
                return redirect(self.success_url)

        return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)


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
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, data=None):
        return self.form_class(data=data, request=self.request, original_appointment=self.original_appointment)

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

        profile = get_profile(request.user)
        new_status = Appointment.Status.REQUESTED if profile and profile.is_patient else Appointment.Status.SCHEDULED
        with transaction.atomic():
            original = Appointment.objects.select_for_update().get(pk=self.original_appointment.pk)
            original.status = Appointment.Status.RESCHEDULED
            original.full_clean()
            original.save(update_fields=["status", "updated_at"])
            new_appointment = Appointment(
                patient=original.patient,
                professional=form.cleaned_data["professional"],
                starts_at=starts_at,
                ends_at=ends_at,
                status=new_status,
                booking_source=profile_booking_source(profile),
                booked_by=request.user,
                rescheduled_from=original,
                service_units=original.service_units,
                notes=form.cleaned_data.get("notes", ""),
            )
            try:
                new_appointment.full_clean()
                new_appointment.save()
            except ValidationError as error:
                add_model_validation_errors(form, error)
                transaction.set_rollback(True)
                return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)

        messages.success(request, "Agendamento reagendado sem consumo de credito.")
        return redirect(self.success_url)


class AppointmentCompleteView(AppointmentAccessMixin, View):
    def post(self, request, pk):
        with transaction.atomic():
            appointment = get_object_or_404(appointments_for_user(request.user).select_for_update(), pk=pk)
            if appointment.status in {Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED}:
                messages.error(request, "Agendamentos cancelados ou reagendados nao consomem credito.")
                return redirect("scheduling:appointments")
            if hasattr(appointment, "service_usage"):
                messages.error(request, "Este atendimento ja foi baixado.")
                return redirect("scheduling:appointments")

            package = (
                ServicePackage.objects.select_for_update()
                .filter(
                    membership__patient=appointment.patient,
                    status=ServicePackage.Status.ACTIVE,
                    used_sessions__lt=F("total_sessions"),
                )
                .order_by("expires_on", "created_at")
                .first()
            )
            if not package:
                messages.error(request, "Nao ha pacote ativo com saldo para este paciente.")
                return redirect("scheduling:appointments")
            if package.remaining_sessions < appointment.service_units:
                messages.error(request, "O pacote nao possui saldo suficiente.")
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
            package.used_sessions += appointment.service_units
            if package.used_sessions >= package.total_sessions:
                package.status = ServicePackage.Status.FINISHED
            package.full_clean()
            package.save()

        messages.success(request, "Atendimento baixado e pacote atualizado.")
        return redirect("scheduling:appointments")


def availabilities_for_user(user):
    queryset = ProfessionalAvailability.objects.select_related("professional")
    if user.is_superuser:
        return queryset
    profile = get_profile(user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
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
        return availabilities_for_user(self.request.user)


class ProfessionalAvailabilityCreateView(FormContextMixin, ProfessionalAvailabilityAccessMixin, CreateView):
    model = ProfessionalAvailability
    form_class = ProfessionalAvailabilityForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:availabilities")
    page_title = "Disponibilidade"
    section_label = "Agenda"
    back_url_name = "scheduling:availabilities"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Disponibilidade cadastrada com sucesso.")
        return super().form_valid(form)


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


class ServicePackageListView(FinanceAccessMixin, SearchableListView, ListView):
    model = ServicePackage
    template_name = "scheduling/package_list.html"
    context_object_name = "packages"
    paginate_by = 12
    search_fields = ["membership__patient__full_name", "membership__plan__name", "status"]

    def get_queryset(self):
        return super().get_queryset().select_related("membership__patient", "membership__plan")


class ServicePackageCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = ServicePackage
    form_class = ServicePackageForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Pacote"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"

    def form_valid(self, form):
        messages.success(self.request, "Pacote cadastrado com sucesso.")
        return super().form_valid(form)


class ServicePackageUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = ServicePackage
    form_class = ServicePackageForm
    template_name = "core/form.html"
    success_url = reverse_lazy("scheduling:packages")
    page_title = "Pacote"
    section_label = "Agenda"
    back_url_name = "scheduling:packages"

    def form_valid(self, form):
        messages.success(self.request, "Pacote atualizado com sucesso.")
        return super().form_valid(form)

# Create your views here.
