from django import forms

from core.forms import StyledModelForm
from patients.models import Patient
from patients.services import sync_professional_patient_assignments
from team.models import Employee, Professional


class EmployeeForm(StyledModelForm):
    class Meta:
        model = Employee
        fields = ["full_name", "photo", "role", "phone", "email", "admission_date", "active"]
        widgets = {"admission_date": forms.DateInput(attrs={"type": "date"})}


class ProfessionalForm(StyledModelForm):
    assigned_patients = forms.ModelMultipleChoiceField(
        label="Pacientes vinculados",
        queryset=Patient.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Marque ou desmarque pacientes vinculados a este profissional. Se ainda nao houver vinculo, deixe todos em branco.",
    )

    class Meta:
        model = Professional
        fields = [
            "full_name",
            "photo",
            "specialty",
            "registration_number",
            "phone",
            "email",
            "bio",
            "active",
            "assigned_patients",
        ]
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_patients"].queryset = Patient.objects.filter(active=True).order_by("full_name")
        if self.instance.pk:
            self.fields["assigned_patients"].initial = Patient.objects.filter(
                professional_assignments__professional=self.instance,
                professional_assignments__active=True,
                active=True,
            )

    def save_patient_assignments(self, professional):
        sync_professional_patient_assignments(professional, self.cleaned_data.get("assigned_patients", []))
