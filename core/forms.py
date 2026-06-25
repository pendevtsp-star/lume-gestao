from django import forms

from core.models import ClinicSettings, GoogleCalendarIntegration, WhatsAppIntegration


class StyledModelForm(forms.ModelForm):
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
            "phone_number_id",
            "business_account_id",
        ]
