import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class AppointmentSeries(TimeStampedModel):
    class RepeatType(models.TextChoices):
        WEEKLY = "weekly", "Semanal"

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_series",
    )
    repeat_type = models.CharField("tipo de repeticao", max_length=20, choices=RepeatType.choices, default=RepeatType.WEEKLY)
    interval_weeks = models.PositiveSmallIntegerField("intervalo em semanas", default=1)
    repeat_until = models.DateField("repetir ate", null=True, blank=True)
    occurrences_count = models.PositiveSmallIntegerField("quantidade de sessoes", default=1)
    notes = models.CharField("observacoes", max_length=180, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "serie de agendamentos"
        verbose_name_plural = "series de agendamentos"

    def __str__(self):
        return f"Serie {self.pk or '-'} - {self.occurrences_count} sessao(oes)"

    def clean(self):
        super().clean()
        if self.interval_weeks < 1:
            raise ValidationError({"interval_weeks": "Use um intervalo de pelo menos 1 semana."})
        if self.occurrences_count < 1:
            raise ValidationError({"occurrences_count": "A serie precisa ter ao menos 1 sessao."})


class Appointment(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Solicitado"
        SCHEDULED = "scheduled", "Agendado"
        COMPLETED = "completed", "Realizado"
        RESCHEDULED = "rescheduled", "Reagendado"
        CANCELED = "canceled", "Cancelado"
        NO_SHOW = "no_show", "Faltou"

    class BookingSource(models.TextChoices):
        PATIENT = "patient", "Paciente"
        PROFESSIONAL = "professional", "Profissional"
        ADMINISTRATION = "administration", "Administracao"
        MANAGEMENT = "management", "Gerencia"

    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="appointments")
    professional = models.ForeignKey("team.Professional", on_delete=models.PROTECT, related_name="appointments")
    service_plan = models.ForeignKey(
        "billing.ServicePlan",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="appointments",
        verbose_name="plano/servico",
    )
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fim")
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    booking_source = models.CharField(
        "origem do agendamento",
        max_length=30,
        choices=BookingSource.choices,
        default=BookingSource.ADMINISTRATION,
    )
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booked_appointments",
    )
    rescheduled_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rescheduled_to",
    )
    series = models.ForeignKey(
        AppointmentSeries,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments",
        verbose_name="serie",
    )
    slot_group = models.CharField("grupo do horario", max_length=36, blank=True, db_index=True)
    slot_capacity = models.PositiveSmallIntegerField("capacidade da sessao", default=1)
    service_units = models.PositiveSmallIntegerField("atendimentos consumidos", default=1)
    notes = models.TextField("observacoes", blank=True)
    external_provider = models.CharField("provedor externo", max_length=40, blank=True)
    external_event_id = models.CharField("id evento externo", max_length=120, blank=True)
    completed_at = models.DateTimeField("baixado em", null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_appointments",
    )

    class Meta:
        ordering = ["starts_at"]
        verbose_name = "agendamento"
        verbose_name_plural = "agendamentos"

    def __str__(self):
        return f"{self.patient} com {self.professional} em {self.starts_at:%d/%m/%Y %H:%M}"

    @property
    def consumes_credit(self):
        return self.status == self.Status.COMPLETED and hasattr(self, "service_usage")

    @property
    def displayed_credit_units(self):
        if self.status in {self.Status.CANCELED, self.Status.RESCHEDULED}:
            return 0
        if self.consumes_credit:
            return self.service_usage.units
        return self.service_units

    @property
    def is_group_session(self):
        return self.slot_capacity > 1

    @property
    def needs_confirmation(self):
        return self.status == self.Status.REQUESTED

    @property
    def is_recurring(self):
        return bool(self.series_id)

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "O fim deve ser posterior ao inicio."})
        if self.service_units < 1:
            raise ValidationError({"service_units": "Informe ao menos 1 atendimento consumido."})
        if self.slot_capacity < 1:
            raise ValidationError({"slot_capacity": "A capacidade da sessao precisa ser de pelo menos 1."})

        if self.starts_at and self.status in {self.Status.REQUESTED, self.Status.SCHEDULED}:
            local_start = timezone.localtime(self.starts_at)
            blocked_event = OperationalCalendarEvent.objects.filter(
                active=True,
                affects_schedule=True,
                event_type__in=[OperationalCalendarEvent.EventType.HOLIDAY, OperationalCalendarEvent.EventType.RECESS],
                starts_on__lte=local_start.date(),
                ends_on__gte=local_start.date(),
            ).first()
            if blocked_event:
                raise ValidationError({"starts_at": f"A agenda esta bloqueada por: {blocked_event.title}."})

        if self.professional_id and self.starts_at and self.ends_at and self.status in {
            self.Status.REQUESTED,
            self.Status.SCHEDULED,
        }:
            overlaps = Appointment.objects.filter(
                professional_id=self.professional_id,
                status__in=[self.Status.REQUESTED, self.Status.SCHEDULED],
                starts_at__lt=self.ends_at,
                ends_at__gt=self.starts_at,
            )
            if self.pk:
                overlaps = overlaps.exclude(pk=self.pk)
            partial_overlaps = overlaps.exclude(starts_at=self.starts_at, ends_at=self.ends_at)
            if partial_overlaps.exists():
                raise ValidationError("Este profissional ja possui atendimento nesse horario.")

            exact_overlaps = overlaps.filter(starts_at=self.starts_at, ends_at=self.ends_at)
            if exact_overlaps.exists():
                existing_capacity = max(appointment.slot_capacity for appointment in exact_overlaps)
                desired_capacity = max(existing_capacity, self.slot_capacity)
                if exact_overlaps.count() + 1 > desired_capacity:
                    raise ValidationError("Este horario ja atingiu a capacidade configurada.")
                existing_group = next((appointment.slot_group for appointment in exact_overlaps if appointment.slot_group), "")
                if self.slot_group and existing_group and self.slot_group != existing_group:
                    raise ValidationError("Este horario ja pertence a outro grupo de sessao.")
                self.slot_capacity = desired_capacity
                self.slot_group = self.slot_group or existing_group or uuid.uuid4().hex
            elif self.slot_capacity > 1 and not self.slot_group:
                self.slot_group = uuid.uuid4().hex
            has_availability = ProfessionalAvailability.objects.filter(
                professional_id=self.professional_id,
                active=True,
            ).exists()
            if has_availability and not ProfessionalAvailability.objects.slot_available(
                professional_id=self.professional_id,
                starts_at=self.starts_at,
                ends_at=self.ends_at,
            ):
                raise ValidationError("Este horario esta fora da disponibilidade recorrente do profissional.")

        if self.status == self.Status.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()


class AppointmentAttendance(TimeStampedModel):
    class Status(models.TextChoices):
        PRESENT = "present", "Presente"
        ABSENT = "absent", "Falta"
        JUSTIFIED_ABSENCE = "justified_absence", "Falta justificada"
        RESCHEDULED = "rescheduled", "Reagendada"
        CLINIC_CANCELED = "clinic_canceled", "Cancelada pela clinica"
        REPLACEMENT = "replacement", "Reposicao"

    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="attendance")
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="attendance_records")
    professional = models.ForeignKey("team.Professional", on_delete=models.PROTECT, related_name="attendance_records")
    status = models.CharField("presenca", max_length=30, choices=Status.choices)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_attendance_records",
    )
    registered_at = models.DateTimeField("registrado em", default=timezone.now)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["-appointment__starts_at"]
        verbose_name = "presenca"
        verbose_name_plural = "presencas"

    def __str__(self):
        return f"{self.patient} - {self.get_status_display()} em {self.appointment.starts_at:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        if self.appointment_id:
            self.patient = self.appointment.patient
            self.professional = self.appointment.professional
        super().save(*args, **kwargs)


class RescheduleRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        APPROVED = "approved", "Aprovada"
        DECLINED = "declined", "Recusada"
        CANCELED = "canceled", "Cancelada"

    class PreferredPeriod(models.TextChoices):
        MORNING = "morning", "Manha"
        AFTERNOON = "afternoon", "Tarde"
        EVENING = "evening", "Noite"
        ANY = "any", "Qualquer horario"

    appointment = models.ForeignKey(Appointment, on_delete=models.PROTECT, related_name="reschedule_requests")
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="reschedule_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_reschedule_requests",
    )
    preferred_date = models.DateField("data preferida", null=True, blank=True)
    preferred_period = models.CharField(
        "periodo preferido",
        max_length=20,
        choices=PreferredPeriod.choices,
        default=PreferredPeriod.ANY,
    )
    reason = models.TextField("motivo", blank=True)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="decided_reschedule_requests",
    )
    decided_at = models.DateTimeField("decidido em", null=True, blank=True)
    decision_note = models.TextField("observacao da equipe", blank=True)
    resolved_appointment = models.ForeignKey(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_reschedule_requests",
    )

    class Meta:
        ordering = ["status", "appointment__starts_at"]
        verbose_name = "solicitacao de remarcacao"
        verbose_name_plural = "solicitacoes de remarcacao"

    def __str__(self):
        return f"{self.patient} - {self.get_status_display()}"

    def clean(self):
        super().clean()
        if self.appointment_id and self.patient_id and self.appointment.patient_id != self.patient_id:
            raise ValidationError({"patient": "A solicitacao deve pertencer ao paciente do agendamento."})


class PatientGoal(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        ACHIEVED = "achieved", "Concluida"
        PAUSED = "paused", "Pausada"
        CANCELED = "canceled", "Cancelada"

    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="goals")
    title = models.CharField("meta", max_length=160)
    main_complaint = models.CharField("queixa principal", max_length=220, blank=True)
    objective = models.TextField("objetivos", blank=True)
    target_date = models.DateField("prazo", null=True, blank=True)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    progress_note = models.TextField("progresso", blank=True)
    achieved_at = models.DateTimeField("concluida em", null=True, blank=True)

    class Meta:
        ordering = ["patient__full_name", "status", "target_date"]
        verbose_name = "meta do paciente"
        verbose_name_plural = "metas dos pacientes"

    def __str__(self):
        return f"{self.patient} - {self.title}"

    def clean(self):
        super().clean()
        if self.status == self.Status.ACHIEVED and not self.achieved_at:
            self.achieved_at = timezone.now()


class PatientAchievement(TimeStampedModel):
    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="achievements")
    goal = models.ForeignKey(PatientGoal, on_delete=models.SET_NULL, null=True, blank=True, related_name="achievements")
    title = models.CharField("conquista", max_length=160)
    description = models.TextField("descricao", blank=True)
    achieved_on = models.DateField("data da conquista", default=timezone.localdate)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_patient_achievements",
    )

    class Meta:
        ordering = ["-achieved_on", "patient__full_name"]
        verbose_name = "conquista do paciente"
        verbose_name_plural = "conquistas dos pacientes"

    def __str__(self):
        return f"{self.patient} - {self.title}"


class PatientCheckIn(TimeStampedModel):
    class Feeling(models.TextChoices):
        NO_PAIN = "no_pain", "Sem dor"
        LIGHT_PAIN = "light_pain", "Dor leve"
        MODERATE_PAIN = "moderate_pain", "Dor moderada"
        INTENSE_PAIN = "intense_pain", "Dor intensa"

    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="checkins")
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkins",
    )
    feeling = models.CharField("como esta se sentindo", max_length=30, choices=Feeling.choices)
    pain_level = models.PositiveSmallIntegerField("nivel de dor", null=True, blank=True)
    note = models.TextField("observacao", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_patient_checkins",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "check-in do paciente"
        verbose_name_plural = "check-ins dos pacientes"

    def __str__(self):
        return f"{self.patient} - {self.get_feeling_display()}"

    def clean(self):
        super().clean()
        if self.pain_level is not None and not 0 <= self.pain_level <= 10:
            raise ValidationError({"pain_level": "Informe um nivel de dor entre 0 e 10."})
        if self.appointment_id and self.patient_id and self.appointment.patient_id != self.patient_id:
            raise ValidationError({"appointment": "O check-in deve pertencer ao paciente do agendamento."})


class PatientNotification(TimeStampedModel):
    class Kind(models.TextChoices):
        APPOINTMENT_DAY = "appointment_day", "Aula no dia"
        SESSION_CONFIRMATION = "session_confirmation", "Confirmacao da sessao"
        ABSENCE_WARNING = "absence_warning", "Aviso de falta"
        PLAN_RENEWAL = "plan_renewal", "Renovacao do plano"
        HOLIDAY = "holiday", "Feriado"
        SCHEDULE_CHANGE = "schedule_change", "Mudanca de horario"
        RESCHEDULE = "reschedule", "Remarcacao"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SENT = "sent", "Enviada"
        SKIPPED = "skipped", "Ignorada"
        FAILED = "failed", "Falhou"

    class Channel(models.TextChoices):
        PANEL = "panel", "Painel"
        WHATSAPP = "whatsapp", "WhatsApp"
        PWA = "pwa", "PWA"

    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="notifications")
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_notifications",
    )
    calendar_event = models.ForeignKey(
        "OperationalCalendarEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name="evento operacional",
    )
    delivery_log = models.OneToOneField(
        "core.WhatsAppMessageLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_notification",
        verbose_name="registro de envio",
    )
    kind = models.CharField("tipo", max_length=30, choices=Kind.choices)
    channel = models.CharField("canal", max_length=20, choices=Channel.choices, default=Channel.PANEL)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.PENDING)
    due_at = models.DateTimeField("programada para", db_index=True)
    sent_at = models.DateTimeField("enviada em", null=True, blank=True)
    idempotency_key = models.CharField("chave unica", max_length=180, unique=True)
    message = models.TextField("mensagem")
    error_message = models.TextField("erro", blank=True)
    attempts = models.PositiveSmallIntegerField("tentativas", default=0)
    last_attempt_at = models.DateTimeField("ultima tentativa", null=True, blank=True)
    provider_reference = models.CharField("referencia do provedor", max_length=120, blank=True)
    metadata = models.JSONField("dados operacionais", default=dict, blank=True)

    class Meta:
        ordering = ["status", "due_at"]
        verbose_name = "notificacao do paciente"
        verbose_name_plural = "notificacoes dos pacientes"

    def __str__(self):
        return f"{self.patient} - {self.get_kind_display()}"


class PatientNotificationPreference(TimeStampedModel):
    patient = models.OneToOneField("patients.Patient", on_delete=models.CASCADE, related_name="notification_preferences")
    whatsapp_enabled = models.BooleanField("aceita WhatsApp", default=True)
    pwa_enabled = models.BooleanField("aceita notificacoes do aplicativo", default=False)
    appointment_enabled = models.BooleanField("aceita avisos de agenda", default=True)
    financial_enabled = models.BooleanField("aceita avisos financeiros", default=True)
    operational_enabled = models.BooleanField("aceita comunicados operacionais", default=True)

    class Meta:
        verbose_name = "preferencia de notificacao"
        verbose_name_plural = "preferencias de notificacao"

    def __str__(self):
        return f"Preferencias de {self.patient}"


class OperationalCalendarEvent(TimeStampedModel):
    class EventType(models.TextChoices):
        HOLIDAY = "holiday", "Feriado"
        RECESS = "recess", "Recesso"
        SPECIAL_HOURS = "special_hours", "Horario especial"
        SCHEDULE_CHANGE = "schedule_change", "Mudanca de horario"

    event_type = models.CharField("tipo", max_length=30, choices=EventType.choices)
    title = models.CharField("titulo", max_length=160)
    starts_on = models.DateField("inicio", default=timezone.localdate)
    ends_on = models.DateField("fim", default=timezone.localdate)
    starts_at_time = models.TimeField("horario de inicio", null=True, blank=True)
    ends_at_time = models.TimeField("horario de fim", null=True, blank=True)
    affects_schedule = models.BooleanField("bloqueia novos agendamentos", default=True)
    send_notice = models.BooleanField("gerar aviso aos pacientes afetados", default=True)
    message = models.TextField("comunicado", blank=True)
    active = models.BooleanField("ativo", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_operational_events",
    )

    class Meta:
        ordering = ["starts_on", "starts_at_time", "title"]
        verbose_name = "evento operacional"
        verbose_name_plural = "eventos operacionais"

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.title}"

    @property
    def blocks_entire_day(self):
        return self.affects_schedule and self.event_type in {self.EventType.HOLIDAY, self.EventType.RECESS}

    def clean(self):
        super().clean()
        if self.ends_on and self.starts_on and self.ends_on < self.starts_on:
            raise ValidationError({"ends_on": "A data final nao pode ser anterior ao inicio."})
        if bool(self.starts_at_time) != bool(self.ends_at_time):
            raise ValidationError("Informe inicio e fim do horario especial.")
        if self.starts_at_time and self.ends_at_time and self.ends_at_time <= self.starts_at_time:
            raise ValidationError({"ends_at_time": "O horario final deve ser posterior ao inicial."})


class ProfessionalAvailabilityQuerySet(models.QuerySet):
    def slot_available(self, professional_id, starts_at, ends_at):
        local_start = timezone.localtime(starts_at)
        local_end = timezone.localtime(ends_at)
        if local_start.date() != local_end.date():
            return False
        return self.filter(
            professional_id=professional_id,
            active=True,
            weekday=local_start.weekday(),
            valid_from__lte=local_start.date(),
            starts_at__lte=local_start.time(),
            ends_at__gte=local_end.time(),
        ).filter(models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=local_start.date())).exists()


class ProfessionalAvailability(TimeStampedModel):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Segunda"
        TUESDAY = 1, "Terca"
        WEDNESDAY = 2, "Quarta"
        THURSDAY = 3, "Quinta"
        FRIDAY = 4, "Sexta"
        SATURDAY = 5, "Sabado"
        SUNDAY = 6, "Domingo"

    professional = models.ForeignKey("team.Professional", on_delete=models.CASCADE, related_name="availabilities")
    weekday = models.PositiveSmallIntegerField("dia da semana", choices=Weekday.choices)
    starts_at = models.TimeField("inicio")
    ends_at = models.TimeField("fim")
    session_capacity = models.PositiveSmallIntegerField("capacidade padrao da sessao", default=1)
    valid_from = models.DateField("valido a partir de", default=timezone.localdate)
    valid_until = models.DateField("valido ate", null=True, blank=True)
    active = models.BooleanField("ativo", default=True)
    deletion_requested_at = models.DateTimeField("exclusao solicitada em", null=True, blank=True)
    notes = models.CharField("observacoes", max_length=180, blank=True)

    objects = ProfessionalAvailabilityQuerySet.as_manager()

    class Meta:
        ordering = ["professional__full_name", "weekday", "starts_at"]
        verbose_name = "disponibilidade profissional"
        verbose_name_plural = "disponibilidades profissionais"
        constraints = [
            models.UniqueConstraint(
                fields=["professional", "weekday", "starts_at", "ends_at", "valid_from"],
                name="unique_professional_availability_window",
            )
        ]

    def __str__(self):
        return f"{self.professional} - {self.get_weekday_display()} {self.starts_at:%H:%M}-{self.ends_at:%H:%M}"

    def clean(self):
        super().clean()
        if self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "O fim deve ser posterior ao inicio."})
        if self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({"valid_until": "A data final nao pode ser anterior ao inicio."})
        if self.session_capacity < 1:
            raise ValidationError({"session_capacity": "Informe uma capacidade de pelo menos 1 paciente."})


class ServicePackage(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ativo"
        FINISHED = "finished", "Finalizado"
        EXPIRED = "expired", "Expirado"
        CANCELED = "canceled", "Cancelado"

    membership = models.ForeignKey("billing.Membership", on_delete=models.PROTECT, related_name="service_packages")
    total_sessions = models.PositiveSmallIntegerField("total de aulas/atendimentos")
    used_sessions = models.PositiveSmallIntegerField("aulas/atendimentos usados", default=0)
    starts_on = models.DateField("inicio", default=timezone.localdate)
    expires_on = models.DateField("validade", null=True, blank=True)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    deletion_requested_at = models.DateTimeField("exclusao solicitada em", null=True, blank=True)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["membership__patient__full_name", "-starts_on"]
        verbose_name = "pacote de atendimentos"
        verbose_name_plural = "pacotes de atendimentos"

    def __str__(self):
        return f"{self.membership.patient} - {self.remaining_sessions}/{self.total_sessions} restantes"

    @property
    def remaining_sessions(self):
        return max(self.total_sessions - self.used_sessions, 0)

    def clean(self):
        super().clean()
        if self.total_sessions < 1:
            raise ValidationError({"total_sessions": "O pacote precisa ter ao menos 1 atendimento."})
        if self.used_sessions > self.total_sessions:
            raise ValidationError({"used_sessions": "Usos nao podem superar o total do pacote."})
        if self.expires_on and self.expires_on < self.starts_on:
            raise ValidationError({"expires_on": "A validade nao pode ser anterior ao inicio."})


class ServiceUsage(TimeStampedModel):
    service_package = models.ForeignKey(ServicePackage, on_delete=models.PROTECT, related_name="usages")
    appointment = models.OneToOneField(Appointment, on_delete=models.PROTECT, related_name="service_usage")
    units = models.PositiveSmallIntegerField("atendimentos consumidos", default=1)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_service_usages",
    )
    registered_at = models.DateTimeField("registrado em", default=timezone.now)

    class Meta:
        ordering = ["-registered_at"]
        verbose_name = "baixa de atendimento"
        verbose_name_plural = "baixas de atendimento"

    def __str__(self):
        return f"{self.appointment} - {self.units}"

    def clean(self):
        super().clean()
        if self.units < 1:
            raise ValidationError({"units": "Informe ao menos 1 atendimento."})
        if self.service_package_id and self.service_package.remaining_sessions < self.units:
            raise ValidationError({"units": "O pacote nao possui saldo suficiente."})


class ServicePackageAdjustment(TimeStampedModel):
    class Reason(models.TextChoices):
        APPOINTMENT_NO_CREDIT = "appointment_no_credit", "Credito adicionado na baixa"
        MANUAL_CORRECTION = "manual_correction", "Correcao manual"

    service_package = models.ForeignKey(ServicePackage, on_delete=models.PROTECT, related_name="adjustments")
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_adjustments",
    )
    delta_sessions = models.SmallIntegerField("ajuste de creditos")
    reason = models.CharField("motivo", max_length=40, choices=Reason.choices, default=Reason.MANUAL_CORRECTION)
    notes = models.TextField("observacoes", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_package_adjustments",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ajuste de credito"
        verbose_name_plural = "ajustes de credito"

    def __str__(self):
        return f"{self.service_package} ({self.delta_sessions:+d})"

    def clean(self):
        super().clean()
        if self.delta_sessions == 0:
            raise ValidationError({"delta_sessions": "O ajuste precisa alterar ao menos 1 credito."})

# Create your models here.
