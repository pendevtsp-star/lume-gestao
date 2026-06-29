from datetime import time

import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.integrations.credentials import configured_value


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
    oauth_client_id = models.CharField("Google Client ID", max_length=255, blank=True)
    oauth_client_secret = models.CharField("Google Client Secret", max_length=255, blank=True)
    access_token = models.TextField("access token", blank=True)
    refresh_token = models.TextField("refresh token", blank=True)
    token_expires_at = models.DateTimeField("token expira em", null=True, blank=True)
    connected_email = models.EmailField("conta conectada", blank=True)
    last_sync_at = models.DateTimeField("ultima sincronizacao", null=True, blank=True)
    last_error = models.TextField("ultimo erro", blank=True)
    calendar_feed_enabled = models.BooleanField("link .ics ativo", default=False)
    calendar_feed_token = models.CharField("token do calendario .ics", max_length=96, blank=True, unique=True)
    calendar_feed_created_at = models.DateTimeField("link .ics criado em", null=True, blank=True)

    class Meta:
        verbose_name = "integracao Google Agenda"
        verbose_name_plural = "integracoes Google Agenda"

    def __str__(self):
        status = "ativa" if self.enabled else "inativa"
        return f"Google Agenda {status}"

    @property
    def is_connected(self):
        return bool(self.enabled and self.refresh_token)

    @property
    def has_calendar_feed(self):
        return bool(self.calendar_feed_enabled and self.calendar_feed_token)

    def regenerate_calendar_feed_token(self):
        self.calendar_feed_token = secrets.token_urlsafe(48)
        self.calendar_feed_enabled = True
        self.calendar_feed_created_at = timezone.now()
        self.save(
            update_fields=[
                "calendar_feed_token",
                "calendar_feed_enabled",
                "calendar_feed_created_at",
                "updated_at",
            ]
        )
        return self.calendar_feed_token

    def revoke_calendar_feed_token(self):
        self.calendar_feed_enabled = False
        self.calendar_feed_token = ""
        self.calendar_feed_created_at = None
        self.save(
            update_fields=[
                "calendar_feed_enabled",
                "calendar_feed_token",
                "calendar_feed_created_at",
                "updated_at",
            ]
        )

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
    clinic_whatsapp_number = models.CharField("numero da clinica", max_length=30, blank=True)
    phone_number_id = models.CharField("ID do numero WhatsApp", max_length=80, blank=True)
    business_account_id = models.CharField("ID da conta WhatsApp Business", max_length=80, blank=True)
    embedded_app_id = models.CharField("Meta App ID", max_length=80, blank=True)
    embedded_config_id = models.CharField("Meta Configuration ID", max_length=120, blank=True)
    embedded_app_secret = models.CharField("Meta App Secret", max_length=255, blank=True)
    access_token = models.TextField("token de acesso Meta", blank=True)
    connected_at = models.DateTimeField("conectado em", null=True, blank=True)
    last_test_at = models.DateTimeField("ultimo teste", null=True, blank=True)
    last_error = models.TextField("ultimo erro", blank=True)

    class Meta:
        verbose_name = "integracao WhatsApp"
        verbose_name_plural = "integracoes WhatsApp"

    def __str__(self):
        status = "ativa" if self.enabled else "inativa"
        return f"{self.get_provider_display()} {status}"

    @property
    def is_connected(self):
        if not self.enabled:
            return False
        if self.provider != self.Provider.META:
            return False
        phone_number_id = configured_value(self.phone_number_id) or configured_value(settings.WHATSAPP_META_PHONE_NUMBER_ID)
        access_token = configured_value(self.access_token) or configured_value(settings.WHATSAPP_META_ACCESS_TOKEN)
        return bool(phone_number_id and (self.dry_run or access_token))

    @classmethod
    def load(cls):
        integration, _ = cls.objects.get_or_create(pk=1)
        return integration


class WhatsAppMessageTemplate(TimeStampedModel):
    class TemplateType(models.TextChoices):
        APPOINTMENT = "appointment", "Mensagem de agendamento"
        CHARGE = "charge", "Mensagem de cobranca"
        BIRTHDAY = "birthday", "Mensagem de aniversario"

    template_type = models.CharField("tipo", max_length=20, choices=TemplateType.choices, unique=True)
    title = models.CharField("titulo", max_length=120)
    description = models.CharField("descricao", max_length=255, blank=True)
    body = models.TextField("mensagem")
    meta_template_name = models.CharField("nome do template aprovado na Meta", max_length=120, blank=True)
    meta_template_language = models.CharField("idioma do template Meta", max_length=10, default="pt_BR")
    send_time = models.TimeField("horario do envio", null=True, blank=True)
    active = models.BooleanField("ativo", default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_templates_updated",
    )

    class Meta:
        ordering = ["template_type"]
        verbose_name = "modelo de mensagem WhatsApp"
        verbose_name_plural = "modelos de mensagens WhatsApp"

    def __str__(self):
        return self.title

    @property
    def variable_tokens(self):
        return self.default_config_for(self.template_type)["tokens"]

    @classmethod
    def default_config_for(cls, template_type):
        return {
            cls.TemplateType.APPOINTMENT: {
                "title": "Mensagem de Agendamento",
                "description": "Lembretes e confirmacoes de sessoes futuras.",
                "body": (
                    "Ola, [Paciente]! Sua sessao com [Profissional] esta agendada para [Data] as [Horario]. "
                    "Se precisar de ajuda, fale com [Clinica] pelo numero [TelefoneClinica]."
                ),
                "tokens": ["[Paciente]", "[Profissional]", "[Data]", "[Horario]", "[Clinica]", "[TelefoneClinica]"],
            },
            cls.TemplateType.CHARGE: {
                "title": "Mensagem de Cobranca",
                "description": "Avisos de mensalidades, pagamentos pendentes e cobrancas avulsas.",
                "body": (
                    "Ola, [Paciente]! Passando para lembrar do valor de [Valor] com vencimento em "
                    "[DataVencimento]. Qualquer duvida, [Profissional] e a equipe da [Clinica] estao a disposicao."
                ),
                "tokens": ["[Paciente]", "[Valor]", "[DataVencimento]", "[Profissional]", "[Clinica]"],
            },
            cls.TemplateType.BIRTHDAY: {
                "title": "Mensagem de Aniversario",
                "description": "Mensagem especial para pacientes ativos na data do aniversario.",
                "body": (
                    "Feliz aniversario, [Paciente]! Que seu novo ciclo seja leve, saudavel e cheio de boas "
                    "conquistas. Com carinho, [Profissional] e a equipe [Clinica]."
                ),
                "tokens": ["[Paciente]", "[Profissional]", "[Clinica]"],
            },
        }[template_type]

    @classmethod
    def ensure_defaults(cls):
        templates = []
        for template_type, _label in cls.TemplateType.choices:
            defaults = cls.default_config_for(template_type)
            template, _created = cls.objects.get_or_create(
                template_type=template_type,
                defaults={
                    "title": defaults["title"],
                    "description": defaults["description"],
                    "body": defaults["body"],
                },
            )
            templates.append(template)
        return templates


class WhatsAppAutomationSettings(TimeStampedModel):
    appointment_reminders_enabled = models.BooleanField("enviar lembretes de consulta automaticamente", default=True)
    appointment_reminder_hours_before = models.PositiveSmallIntegerField("horas antes da consulta", default=24)
    birthday_messages_enabled = models.BooleanField("enviar aniversarios automaticamente", default=True)
    birthday_send_time = models.TimeField("horario do aniversario", default=time(8, 0))
    membership_due_reminders_enabled = models.BooleanField("enviar lembretes de mensalidade a vencer", default=True)
    membership_due_days_before = models.PositiveSmallIntegerField("dias antes do vencimento", default=3)
    membership_due_on_date = models.BooleanField("enviar tambem no dia do vencimento", default=True)
    membership_overdue_enabled = models.BooleanField("enviar aviso de mensalidade vencida", default=True)
    membership_overdue_days_after = models.PositiveSmallIntegerField("dias apos o vencimento", default=1)
    charge_overdue_enabled = models.BooleanField("enviar aviso de cobranca avulsa vencida", default=True)
    charge_overdue_days_after = models.PositiveSmallIntegerField("dias apos vencimento avulso", default=1)

    class Meta:
        verbose_name = "automacao WhatsApp"
        verbose_name_plural = "automacoes WhatsApp"

    def __str__(self):
        return "Automacoes WhatsApp"

    @classmethod
    def load(cls):
        settings_object, _ = cls.objects.get_or_create(pk=1)
        return settings_object


class WhatsAppMessageLog(TimeStampedModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Agendada"
        SENT = "sent", "Enviada"
        DRY_RUN = "dry_run", "Simulada"
        FAILED = "failed", "Falhou"
        CANCELED = "canceled", "Cancelada"

    integration = models.ForeignKey(
        WhatsAppIntegration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_logs",
    )
    template = models.ForeignKey(
        WhatsAppMessageTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_logs",
    )
    appointment = models.ForeignKey(
        "scheduling.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_logs",
    )
    payment = models.ForeignKey(
        "billing.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_logs",
    )
    charge = models.ForeignKey(
        "billing.Charge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_logs",
    )
    recipient_name = models.CharField("destinatario", max_length=180)
    recipient_number = models.CharField("numero", max_length=30)
    rendered_message = models.TextField("mensagem enviada")
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.DRY_RUN)
    scheduled_for = models.DateTimeField("agendada para", null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField("enviada em", null=True, blank=True)
    provider_reference = models.CharField("referencia do provedor", max_length=120, blank=True)
    error_message = models.TextField("erro", blank=True)
    response_payload = models.JSONField("retorno da integracao", default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "historico de WhatsApp"
        verbose_name_plural = "historico de WhatsApp"

    def __str__(self):
        return f"{self.recipient_name} - {self.get_status_display()}"


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
