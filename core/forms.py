from django import forms
from django.utils import timezone

from billing.models import Charge, Payment
from core.models import (
    ClinicSettings,
    GoogleCalendarIntegration,
    WhatsAppAutomationSettings,
    WhatsAppIntegration,
    WhatsAppMessageTemplate,
)
from patients.models import Patient
from scheduling.models import Appointment


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
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
    class Meta:
        model = GoogleCalendarIntegration
        fields = ["enabled", "calendar_id", "sync_on_save"]


class WhatsAppIntegrationForm(StyledModelForm):
    class Meta:
        model = WhatsAppIntegration
        fields = [
            "enabled",
            "dry_run",
            "provider",
            "default_country_code",
            "clinic_whatsapp_number",
            "phone_number_id",
            "business_account_id",
        ]


class WhatsAppMessageTemplateForm(StyledModelForm):
    class Meta:
        model = WhatsAppMessageTemplate
        fields = ["active", "title", "description", "body", "send_time"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5}),
            "send_time": forms.TimeInput(attrs={"type": "time"}),
        }


class WhatsAppAutomationSettingsForm(StyledModelForm):
    class Meta:
        model = WhatsAppAutomationSettings
        fields = [
            "appointment_reminders_enabled",
            "appointment_reminder_hours_before",
            "birthday_messages_enabled",
            "birthday_send_time",
        ]
        widgets = {
            "birthday_send_time": forms.TimeInput(attrs={"type": "time"}),
        }


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
            Payment.objects.select_related("membership__patient", "membership__plan")
            .filter(status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE])
            .order_by("due_date")[:40]
        )
        for payment in payments:
            key = f"payment:{payment.pk}"
            self.reference_map[key] = payment
            choices.append(
                (
                    key,
                    f"Mensalidade - {payment.membership.patient.full_name} - "
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
