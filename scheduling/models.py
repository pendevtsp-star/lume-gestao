from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Appointment(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Solicitado"
        SCHEDULED = "scheduled", "Agendado"
        COMPLETED = "completed", "Realizado"
        CANCELED = "canceled", "Cancelado"
        NO_SHOW = "no_show", "Faltou"

    class BookingSource(models.TextChoices):
        PATIENT = "patient", "Paciente"
        PROFESSIONAL = "professional", "Profissional"
        ADMINISTRATION = "administration", "Administracao"
        MANAGEMENT = "management", "Gerencia"

    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="appointments")
    professional = models.ForeignKey("team.Professional", on_delete=models.PROTECT, related_name="appointments")
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

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "O fim deve ser posterior ao inicio."})
        if self.service_units < 1:
            raise ValidationError({"service_units": "Informe ao menos 1 atendimento consumido."})

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
            if overlaps.exists():
                raise ValidationError("Este profissional ja possui atendimento nesse horario.")

        if self.status == self.Status.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()


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

# Create your models here.
