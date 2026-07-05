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
