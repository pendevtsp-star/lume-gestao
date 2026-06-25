from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class ClinicSettings(TimeStampedModel):
    clinic_name = models.CharField("nome da clinica", max_length=140, default="Lume Gestao")
    cnpj = models.CharField("CNPJ", max_length=18, blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    address = models.CharField("endereco", max_length=255, blank=True)
    logo = models.FileField("logo", upload_to="clinic/", blank=True)
    business_days = models.CharField("dias de atendimento", max_length=120, default="Segunda a sexta")
    opening_time = models.TimeField("horario de abertura", default=time(8, 0))
    closing_time = models.TimeField("horario de fechamento", default=time(18, 0))
    membership_due_reminder_days = models.PositiveSmallIntegerField(
        "dias antes do vencimento",
        default=5,
        help_text="Quantidade de dias para destacar mensalidades proximas do vencimento.",
    )
    default_membership_due_day = models.PositiveSmallIntegerField(
        "dia padrao de vencimento",
        default=10,
        help_text="Dia sugerido para novas mensalidades. Use entre 1 e 28.",
    )
    cancellation_deadline_hours = models.PositiveSmallIntegerField(
        "prazo de cancelamento em horas",
        default=24,
        help_text="Prazo minimo recomendado para cancelar sem intervencao da equipe.",
    )
    rescheduling_deadline_hours = models.PositiveSmallIntegerField(
        "prazo de reagendamento em horas",
        default=24,
        help_text="Prazo minimo recomendado para reagendar sem intervencao da equipe.",
    )
    cancellation_policy = models.TextField("regra de cancelamento", blank=True)
    rescheduling_policy = models.TextField("regra de reagendamento", blank=True)

    class Meta:
        verbose_name = "configuracao da clinica"
        verbose_name_plural = "configuracoes da clinica"

    def __str__(self):
        return self.clinic_name

    def clean(self):
        super().clean()
        digits = "".join(character for character in (self.cnpj or "") if character.isdigit())
        if digits and len(digits) != 14:
            raise ValidationError({"cnpj": "Informe um CNPJ com 14 digitos."})
        self.cnpj = digits
        if self.opening_time and self.closing_time and self.closing_time <= self.opening_time:
            raise ValidationError({"closing_time": "O fechamento deve ser posterior a abertura."})
        if not 1 <= self.membership_due_reminder_days <= 60:
            raise ValidationError({"membership_due_reminder_days": "Informe entre 1 e 60 dias."})
        if not 1 <= self.default_membership_due_day <= 28:
            raise ValidationError({"default_membership_due_day": "Use um vencimento entre os dias 1 e 28."})

    @classmethod
    def load(cls):
        settings_object, _ = cls.objects.get_or_create(pk=1)
        return settings_object


class GoogleCalendarIntegration(TimeStampedModel):
    calendar_id = models.CharField("agenda Google", max_length=180, default="primary")
    enabled = models.BooleanField("ativa", default=False)
    sync_on_save = models.BooleanField("sincronizar novos agendamentos", default=True)
    access_token = models.TextField("access token", blank=True)
    refresh_token = models.TextField("refresh token", blank=True)
    token_expires_at = models.DateTimeField("token expira em", null=True, blank=True)
    connected_email = models.EmailField("conta conectada", blank=True)
    last_sync_at = models.DateTimeField("ultima sincronizacao", null=True, blank=True)
    last_error = models.TextField("ultimo erro", blank=True)

    class Meta:
        verbose_name = "integracao Google Agenda"
        verbose_name_plural = "integracoes Google Agenda"

    def __str__(self):
        status = "ativa" if self.enabled else "inativa"
        return f"Google Agenda {status}"

    @property
    def is_connected(self):
        return bool(self.enabled and self.refresh_token)

    @classmethod
    def load(cls):
        integration, _ = cls.objects.get_or_create(pk=1)
        return integration


class WhatsAppIntegration(TimeStampedModel):
    class Provider(models.TextChoices):
        META = "meta", "Meta Cloud API"
        TWILIO = "twilio", "Twilio"

    provider = models.CharField("provedor", max_length=20, choices=Provider.choices, default=Provider.META)
    enabled = models.BooleanField("ativa", default=False)
    dry_run = models.BooleanField("modo teste", default=True)
    default_country_code = models.CharField("codigo do pais", max_length=4, default="55")
    phone_number_id = models.CharField("ID do numero WhatsApp", max_length=80, blank=True)
    business_account_id = models.CharField("ID da conta WhatsApp Business", max_length=80, blank=True)
    last_test_at = models.DateTimeField("ultimo teste", null=True, blank=True)
    last_error = models.TextField("ultimo erro", blank=True)

    class Meta:
        verbose_name = "integracao WhatsApp"
        verbose_name_plural = "integracoes WhatsApp"

    def __str__(self):
        status = "ativa" if self.enabled else "inativa"
        return f"{self.get_provider_display()} {status}"

    @classmethod
    def load(cls):
        integration, _ = cls.objects.get_or_create(pk=1)
        return integration


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Criado"
        UPDATED = "updated", "Atualizado"
        DELETED = "deleted", "Excluido"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField("acao", max_length=20, choices=Action.choices)
    app_label = models.CharField("app", max_length=80)
    model_name = models.CharField("modelo", max_length=80)
    object_id = models.CharField("id do objeto", max_length=80, blank=True)
    object_repr = models.CharField("objeto", max_length=255)
    changes = models.JSONField("alteracoes", default=dict, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"

    def __str__(self):
        return f"{self.get_action_display()} {self.model_name} #{self.object_id}"

# Create your models here.
