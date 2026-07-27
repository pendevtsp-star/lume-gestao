"""Agenda listing, calendar export, and appointment creation views."""

from scheduling.web.common import *  # noqa: F401,F403

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
    slot_confirm_label = "Confirmar agendamento"

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
            "slot_confirm_label": self.slot_confirm_label,
            "original_appointment": getattr(self, "original_appointment", None),
            "has_future_series": getattr(self, "has_future_series", False),
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
            snapshot = slot_availability_snapshot(
                form.cleaned_data["professional"],
                starts_at,
                ends_at,
                exclude_appointment_id=getattr(exclude_appointment, "pk", None),
            )
            if snapshot["capacity"] and snapshot["remaining_capacity"] <= 0:
                form.add_error(None, "Esta sessao ja atingiu a capacidade maxima. Escolha outro horario livre.")
            elif not snapshot["availability_matches"]:
                form.add_error(None, "Este horario esta fora da disponibilidade do profissional. Escolha outro horario livre.")
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
                status = Appointment.Status.REQUESTED if profile and profile.is_patient else Appointment.Status.SCHEDULED
                try:
                    with transaction.atomic():
                        lock_professional_schedule(form.cleaned_data["professional"])
                        occurrence_payloads = build_occurrence_payloads(
                            professional=form.cleaned_data["professional"],
                            patient_ids=[patient.pk for patient in patients],
                            dates=recurrence_dates,
                            selected_start=timezone.localtime(starts_at).time(),
                            duration_minutes=form.cleaned_data["duration_minutes"],
                            requested_capacity=form.cleaned_data["session_capacity"],
                        )
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
                                appointment.full_clean()
                                appointment.save()
                                created_count += 1
                        first_created_day = timezone.localtime(occurrence_payloads[0]["starts_at"]).date()
                except ValidationError as error:
                    add_model_validation_errors(form, error)
                    return self.render_slot_page(form, slots=slots, searched=True, booking_values=booking_values)

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
