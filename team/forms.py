from django import forms

from core.forms import StyledModelForm
from team.models import Employee, Professional


class EmployeeForm(StyledModelForm):
    class Meta:
        model = Employee
        fields = ["full_name", "photo", "role", "phone", "email", "admission_date", "active"]
        widgets = {"admission_date": forms.DateInput(attrs={"type": "date"})}


class ProfessionalForm(StyledModelForm):
    class Meta:
        model = Professional
        fields = ["full_name", "photo", "specialty", "registration_number", "phone", "email", "bio", "active"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}
