"""Appointment rescheduling, attendance, and patient progress views."""

from scheduling.web.common import *  # noqa: F401,F403
from scheduling.web.agenda_creation import SlotSelectionMixin

class AppointmentRescheduleView(SlotSelectionMixin, AppointmentAccessMixin, FormView):
    form_class = AppointmentRescheduleSlotForm
    success_url = reverse_lazy("scheduling:appointments")
    page_title = "Reagendamento"
    submit_label = "Ver novos horarios"
    slot_select_label = "Reagendar para este horario"
    slot_confirm_label = "Confirmar reagendamento"

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
                lock_professional_schedule(form.cleaned_data["professional"])
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
                lock_professional_schedule(form.cleaned_data["professional"])
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
