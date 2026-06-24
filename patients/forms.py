from django import forms

from core.forms import StyledModelForm
from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment


class PatientForm(StyledModelForm):
    class Meta:
        model = Patient
        fields = [
            "full_name",
            "cpf",
            "birth_date",
            "phone",
            "email",
            "emergency_contact",
            "address",
            "clinical_notes",
            "active",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "clinical_notes": forms.Textarea(attrs={"rows": 4}),
        }


class ProfessionalPatientAssignmentForm(StyledModelForm):
    class Meta:
        model = ProfessionalPatientAssignment
        fields = ["patient", "professional", "active", "notes"]


class ProfessionalNoteForm(StyledModelForm):
    class Meta:
        model = ProfessionalNote
        fields = ["patient", "professional", "title", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}
