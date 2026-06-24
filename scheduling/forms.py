from django import forms

from accounts.models import UserProfile
from accounts.permissions import get_profile
from core.forms import StyledModelForm
from patients.models import ProfessionalPatientAssignment
from scheduling.models import Appointment, ServicePackage
from team.models import Professional


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


class ServicePackageForm(StyledModelForm):
    class Meta:
        model = ServicePackage
        fields = ["membership", "total_sessions", "used_sessions", "starts_on", "expires_on", "status", "notes"]
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "expires_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
