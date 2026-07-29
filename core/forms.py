from django import forms
from django.utils import timezone

from billing.models import Charge, Payment
from core.models import (
    ClinicSettings,
    GoogleCalendarIntegration,
    WhatsAppAutomationSettings,
    WhatsAppAutomationRule,
    WhatsAppIntegration,
    WhatsAppMessageTemplate,
)
from patients.models import Patient
from scheduling.models import Appointment
from core.validators import validate_image_upload


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.ImageField) and validate_image_upload not in field.validators:
                field.validators.append(validate_image_upload)
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
            else:
                widget.attrs.setdefault("class", "field-control")


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
            else:
                widget.attrs.setdefault("class", "field-control")


class ClinicSettingsForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if validate_image_upload not in self.fields["logo"].validators:
            self.fields["logo"].validators.append(validate_image_upload)

    class Meta:
        model = ClinicSettings
        fields = [
            "clinic_name",
            "cnpj",
            "phone",
            "email",
            "address",
            "logo",
            "business_days",
            "opening_time",
            "closing_time",
            "membership_due_reminder_days",
            "default_membership_due_day",
            "cancellation_deadline_hours",
            "rescheduling_deadline_hours",
            "cancellation_policy",
            "rescheduling_policy",
        ]
        widgets = {
            "opening_time": forms.TimeInput(attrs={"type": "time"}),
            "closing_time": forms.TimeInput(attrs={"type": "time"}),
            "cancellation_policy": forms.Textarea(attrs={"rows": 4}),
            "rescheduling_policy": forms.Textarea(attrs={"rows": 4}),
        }


class GoogleCalendarIntegrationForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["oauth_client_id"].label = "Google Client ID (nao e e-mail)"
        self.fields["oauth_client_secret"].label = "Google Client Secret (nao e senha)"
        self.fields["oauth_client_id"].help_text = "Cole aqui o Client ID criado no Google Cloud."
        self.fields["oauth_client_secret"].help_text = "Cole aqui o Client Secret criado no Google Cloud. Nunca use a senha da conta Google."

    def clean_oauth_client_secret(self):
        value = self.cleaned_data.get("oauth_client_secret")
        if not value and self.instance and self.instance.pk:
            return self.instance.oauth_client_secret
        return value

    class Meta:
        model = GoogleCalendarIntegration
        fields = ["enabled", "calendar_id", "sync_on_save", "oauth_client_id", "oauth_client_secret"]
        widgets = {
            "oauth_client_secret": forms.PasswordInput(render_value=False),
        }


class WhatsAppIntegrationForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["clinic_whatsapp_number"].label = "Numero oficial da clinica"
        self.fields["default_country_code"].label = "DDI"
        self.fields["enabled"].label = "Ativar integracao"
        self.fields["dry_run"].label = "Manter em modo teste"
        self.fields["clinic_whatsapp_number"].help_text = "Use o numero do WhatsApp Business que sera pareado pelo QR."

    class Meta:
        model = WhatsAppIntegration
        fields = [
            "enabled",
            "dry_run",
            "default_country_code",
            "clinic_whatsapp_number",
        ]


class WhatsAppTemplateBodyValidationMixin:
    def clean_body(self):
        from core.services.whatsapp_configuration import validate_template_body

        template_type = (
            getattr(self.instance, "template_type", "")
            or WhatsAppMessageTemplate.TemplateType.CUSTOM
        )
        return validate_template_body(template_type, self.cleaned_data.get("body"))


class WhatsAppMessageTemplateForm(WhatsAppTemplateBodyValidationMixin, StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].help_text = (
            "Use somente as variaveis documentadas. A previa ao lado mostra o texto preenchido."
        )
        self.fields["body"].widget.attrs.update(
            {
                "data-whatsapp-template-body": "",
                "data-template-type": getattr(self.instance, "template_type", ""),
            }
        )

    class Meta:
        model = WhatsAppMessageTemplate
        fields = [
            "active",
            "title",
            "description",
            "body",
            "send_time",
        ]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5}),
            "send_time": forms.TimeInput(attrs={"type": "time"}),
        }


class RelationshipAutomationForm(StyledForm):
    enabled = forms.BooleanField(label="Automação ativa", required=False)
    timing = forms.IntegerField(required=False, min_value=0, max_value=168)
    send_time = forms.TimeField(
        label="Horário do envio",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    body = forms.CharField(
        label="Texto da mensagem",
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    def __init__(self, *args, template_type, timing_kind="none", timing_label="", **kwargs):
        self.template_type = template_type
        super().__init__(*args, **kwargs)
        if timing_kind == "time":
            self.fields.pop("timing")
        elif timing_kind in {"hours", "days"}:
            self.fields.pop("send_time")
            self.fields["timing"].label = timing_label
        else:
            self.fields.pop("timing")
            self.fields.pop("send_time")

    def clean_body(self):
        from core.services.whatsapp_configuration import validate_template_body

        return validate_template_body(self.template_type, self.cleaned_data.get("body"))


class CustomWhatsAppMessageTemplateForm(WhatsAppTemplateBodyValidationMixin, StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].help_text = "Use somente as variaveis documentadas abaixo."

    class Meta:
        model = WhatsAppMessageTemplate
        fields = ["title", "description", "body", "active"]
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}


class WhatsAppAutomationSettingsForm(StyledModelForm):
    class Meta:
        model = WhatsAppAutomationSettings
        fields = [
            "appointment_reminders_enabled",
            "appointment_reminder_hours_before",
            "appointment_day_reminders_enabled",
            "appointment_day_reminder_hours_before",
            "birthday_messages_enabled",
            "birthday_send_time",
            "membership_due_reminders_enabled",
            "membership_due_days_before",
            "membership_due_on_date",
            "membership_overdue_enabled",
            "membership_overdue_days_after",
            "charge_overdue_enabled",
            "charge_overdue_days_after",
            "package_expiry_reminders_enabled",
            "package_expiry_days_before",
            "low_credit_reminders_enabled",
            "low_credit_threshold",
        ]
        widgets = {
            "birthday_send_time": forms.TimeInput(attrs={"type": "time"}),
        }


class WhatsAppAutomationRuleForm(StyledModelForm):
    AUTOMATIC_TEMPLATE_TYPES = {
        WhatsAppMessageTemplate.TemplateType.APPOINTMENT,
        WhatsAppMessageTemplate.TemplateType.SESSION_SOON,
        WhatsAppMessageTemplate.TemplateType.CUSTOM,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = WhatsAppMessageTemplate.objects.filter(active=True).order_by("title")
        self.fields["hours_before"].help_text = "Informe quantas horas antes da sessao a fila deve criar o envio."

    class Meta:
        model = WhatsAppAutomationRule
        fields = ["name", "template", "trigger", "hours_before", "active"]
        widgets = {
            "trigger": forms.Select(),
        }

    def clean(self):
        cleaned_data = super().clean()
        trigger = cleaned_data.get("trigger")
        template = cleaned_data.get("template")
        if trigger == WhatsAppAutomationRule.Trigger.MANUAL:
            cleaned_data["hours_before"] = 0
        elif trigger == WhatsAppAutomationRule.Trigger.APPOINTMENT_BEFORE:
            if template and template.template_type not in self.AUTOMATIC_TEMPLATE_TYPES:
                self.add_error(
                    "template",
                    "Escolha um modelo de agenda, sessao proxima ou personalizado para esta rotina.",
                )
            if not cleaned_data.get("hours_before"):
                self.add_error("hours_before", "Informe quantas horas antes da sessao o envio deve ocorrer.")
        return cleaned_data


class WhatsAppDeliveryForm(StyledForm):
    SEND_NOW = "now"
    SEND_SCHEDULED = "schedule"

    send_mode = forms.ChoiceField(
        label="Quando enviar",
        choices=[
            (SEND_NOW, "Enviar agora"),
            (SEND_SCHEDULED, "Agendar para depois"),
        ],
        initial=SEND_NOW,
        required=False,
    )
    scheduled_for = forms.DateTimeField(
        label="Data e hora do envio",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    custom_number = forms.CharField(label="Numero para envio", max_length=30, required=False)

    def clean(self):
        cleaned_data = super().clean()
        send_mode = cleaned_data.get("send_mode") or self.SEND_NOW
        cleaned_data["send_mode"] = send_mode
        scheduled_for = cleaned_data.get("scheduled_for")
        if send_mode == self.SEND_SCHEDULED:
            if not scheduled_for:
                self.add_error("scheduled_for", "Informe a data e hora do envio agendado.")
            elif scheduled_for <= timezone.now():
                self.add_error("scheduled_for", "Escolha um horario futuro para agendar a mensagem.")
        return cleaned_data


class WhatsAppAppointmentSendForm(WhatsAppDeliveryForm):
    appointment = forms.ModelChoiceField(label="Agendamento", queryset=Appointment.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["appointment"].queryset = (
            Appointment.objects.select_related("patient", "professional")
            .filter(status__in=[Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED])
            .order_by("starts_at")
        )
        self.fields["appointment"].label_from_instance = (
            lambda appointment: (
                f"{appointment.patient.full_name} - {appointment.professional.full_name} - "
                f"{appointment.starts_at:%d/%m/%Y %H:%M}"
            )
        )


class WhatsAppChargeSendForm(WhatsAppDeliveryForm):
    reference = forms.ChoiceField(label="Cobranca")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reference_map = {}
        choices = []
        payments = (
            Payment.objects.select_related("patient", "membership__patient", "membership__plan")
            .filter(status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE])
            .order_by("due_date")[:40]
        )
        for payment in payments:
            key = f"payment:{payment.pk}"
            self.reference_map[key] = payment
            choices.append(
                (
                    key,
                    f"{payment.item_display} - {payment.patient_display} - "
                    f"{payment.due_date:%d/%m/%Y} - R$ {payment.amount:.2f}",
                )
            )
        charges = (
            Charge.objects.select_related("patient")
            .filter(status__in=[Charge.Status.OPEN, Charge.Status.OVERDUE])
            .order_by("due_date")[:40]
        )
        for charge in charges:
            patient_name = charge.patient.full_name if charge.patient_id else "Sem paciente"
            key = f"charge:{charge.pk}"
            self.reference_map[key] = charge
            choices.append(
                (
                    key,
                    f"Cobranca avulsa - {patient_name} - {charge.due_date:%d/%m/%Y} - R$ {charge.amount:.2f}",
                )
            )
        self.fields["reference"].choices = choices

    def clean_reference(self):
        reference = self.cleaned_data["reference"]
        if reference not in self.reference_map:
            raise forms.ValidationError("Selecione uma cobranca valida.")
        self.selected_reference = self.reference_map[reference]
        return reference


class WhatsAppBirthdaySendForm(WhatsAppDeliveryForm):
    patient = forms.ModelChoiceField(label="Paciente", queryset=Patient.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = (
            Patient.objects.filter(active=True, birth_date__isnull=False).order_by("full_name")[:80]
        )
