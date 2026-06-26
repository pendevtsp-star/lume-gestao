from django import forms
from django.utils import timezone

from accounts.models import UserProfile
from accounts.permissions import get_profile
from core.forms import StyledModelForm
from core.models import ClinicSettings
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage
from team.models import Professional


DURATION_CHOICES = [
    (30, "30 minutos"),
    (45, "45 minutos"),
    (60, "1 hora"),
    (90, "1 hora e 30 minutos"),
]


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
            elif isinstance(widget, forms.HiddenInput):
                continue
            else:
                widget.attrs.setdefault("class", "field-control")


def visible_patients_for_request(request):
    queryset = Patient.objects.filter(active=True)
    if not request:
        return queryset
    if request.user.is_superuser:
        return queryset

    profile = get_profile(request.user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_patient and profile.patient_id:
        return queryset.filter(pk=profile.patient_id)
    if profile.is_professional and profile.professional_id:
        patient_ids = ProfessionalPatientAssignment.objects.filter(
            professional=profile.professional,
            active=True,
        ).values_list("patient_id", flat=True)
        return queryset.filter(pk__in=patient_ids)
    return queryset.none()


def visible_professionals_for_request(request, patient=None):
    queryset = Professional.objects.filter(active=True)
    if not request:
        return queryset
    if request.user.is_superuser:
        return queryset

    profile = get_profile(request.user)
    if not profile:
        return queryset.none()
    if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
        return queryset
    if profile.is_professional and profile.professional_id:
        return queryset.filter(pk=profile.professional_id)
    if profile.is_patient and profile.patient_id:
        patient = patient or profile.patient
        professional_ids = ProfessionalPatientAssignment.objects.filter(
            patient=patient,
            active=True,
        ).values_list("professional_id", flat=True)
        return queryset.filter(pk__in=professional_ids)
    return queryset.none()


class AppointmentForm(StyledModelForm):
    class Meta:
        model = Appointment
        fields = ["patient", "professional", "starts_at", "ends_at", "status", "service_units", "notes"]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        if not self.request:
            return

        profile = get_profile(self.request.user)
        if not profile or self.request.user.is_superuser or profile.role in {
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
        }:
            return

        if profile.is_patient and profile.patient_id:
            self.fields["patient"].queryset = self.fields["patient"].queryset.filter(pk=profile.patient_id)
            professional_ids = ProfessionalPatientAssignment.objects.filter(
                patient=profile.patient,
                active=True,
            ).values_list("professional_id", flat=True)
            self.fields["professional"].queryset = Professional.objects.filter(pk__in=professional_ids, active=True)
            self.fields["status"].choices = [
                (Appointment.Status.REQUESTED, "Solicitado"),
                (Appointment.Status.CANCELED, "Cancelado"),
            ]

        if profile.is_professional and profile.professional_id:
            self.fields["professional"].queryset = self.fields["professional"].queryset.filter(pk=profile.professional_id)
            patient_ids = ProfessionalPatientAssignment.objects.filter(
                professional=profile.professional,
                active=True,
            ).values_list("patient_id", flat=True)
            self.fields["patient"].queryset = self.fields["patient"].queryset.filter(pk__in=patient_ids)


class AppointmentRescheduleForm(StyledModelForm):
    class Meta:
        model = Appointment
        fields = ["professional", "starts_at", "ends_at", "notes"]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.original_appointment = kwargs.pop("original_appointment", None)
        super().__init__(*args, **kwargs)
        if self.original_appointment:
            self.fields["professional"].initial = self.original_appointment.professional
            self.fields["notes"].initial = self.original_appointment.notes

        if not self.request:
            return

        profile = get_profile(self.request.user)
        if profile and profile.is_professional and profile.professional_id:
            self.fields["professional"].queryset = Professional.objects.filter(pk=profile.professional_id, active=True)
        elif profile and profile.is_patient and profile.patient_id and self.original_appointment:
            professional_ids = ProfessionalPatientAssignment.objects.filter(
                patient=self.original_appointment.patient,
                active=True,
            ).values_list("professional_id", flat=True)
            self.fields["professional"].queryset = Professional.objects.filter(pk__in=professional_ids, active=True)


class AppointmentSlotSearchForm(StyledForm):
    patient = forms.ModelChoiceField(label="Paciente", queryset=Patient.objects.none())
    professional = forms.ModelChoiceField(label="Profissional", queryset=Professional.objects.none())
    appointment_date = forms.DateField(
        label="Data",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    duration_minutes = forms.ChoiceField(label="Duracao", choices=DURATION_CHOICES, initial=60)
    service_units = forms.IntegerField(label="Creditos previstos", min_value=1, initial=1)
    notes = forms.CharField(
        label="Observacoes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    selected_start = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = visible_patients_for_request(self.request)
        self.fields["professional"].queryset = visible_professionals_for_request(self.request)

        if self.request:
            profile = get_profile(self.request.user)
            if profile and profile.is_patient and profile.patient_id:
                self.fields["patient"].initial = profile.patient
                self.fields["patient"].widget = forms.HiddenInput()
            if profile and profile.is_professional and profile.professional_id:
                self.fields["professional"].initial = profile.professional
                self.fields["professional"].widget = forms.HiddenInput()

    def clean_duration_minutes(self):
        return int(self.cleaned_data["duration_minutes"])

    def clean(self):
        cleaned_data = super().clean()
        patient = cleaned_data.get("patient")
        professional = cleaned_data.get("professional")
        if self.request and patient and professional:
            allowed_professionals = visible_professionals_for_request(self.request, patient=patient)
            if not allowed_professionals.filter(pk=professional.pk).exists():
                raise forms.ValidationError("Este profissional nao esta disponivel para este paciente.")
        return cleaned_data


class AppointmentRescheduleSlotForm(StyledForm):
    professional = forms.ModelChoiceField(label="Profissional", queryset=Professional.objects.none())
    appointment_date = forms.DateField(
        label="Nova data",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    duration_minutes = forms.ChoiceField(label="Duracao", choices=DURATION_CHOICES, initial=60)
    notes = forms.CharField(
        label="Observacoes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    selected_start = forms.TimeField(
        required=False,
        input_formats=["%H:%M"],
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.original_appointment = kwargs.pop("original_appointment", None)
        super().__init__(*args, **kwargs)
        patient = self.original_appointment.patient if self.original_appointment else None
        self.fields["professional"].queryset = visible_professionals_for_request(self.request, patient=patient)

        if self.original_appointment:
            self.fields["professional"].initial = self.original_appointment.professional
            self.fields["appointment_date"].initial = timezone.localtime(self.original_appointment.starts_at).date()
            duration = self.original_appointment.ends_at - self.original_appointment.starts_at
            self.fields["duration_minutes"].initial = int(duration.total_seconds() // 60)
            self.fields["notes"].initial = self.original_appointment.notes

        if self.request:
            profile = get_profile(self.request.user)
            if profile and profile.is_professional and profile.professional_id:
                self.fields["professional"].initial = profile.professional
                self.fields["professional"].widget = forms.HiddenInput()

    def clean_duration_minutes(self):
        return int(self.cleaned_data["duration_minutes"])


class ProfessionalAvailabilityForm(StyledModelForm):
    class Meta:
        model = ProfessionalAvailability
        fields = ["professional", "weekday", "starts_at", "ends_at", "valid_from", "valid_until", "active", "notes"]
        widgets = {
            "starts_at": forms.TimeInput(attrs={"type": "time"}),
            "ends_at": forms.TimeInput(attrs={"type": "time"}),
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        if not self.request:
            return
        profile = get_profile(self.request.user)
        if profile and profile.is_professional and profile.professional_id:
            self.fields["professional"].queryset = Professional.objects.filter(pk=profile.professional_id, active=True)


class ServicePackageForm(StyledModelForm):
    class Meta:
        model = ServicePackage
        fields = ["membership", "total_sessions", "used_sessions", "starts_on", "expires_on", "status", "notes"]
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "expires_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class AgendaSettingsForm(StyledModelForm):
    class Meta:
        model = ClinicSettings
        fields = [
            "opening_time",
            "closing_time",
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
