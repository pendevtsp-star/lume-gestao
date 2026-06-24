from django import forms
from django.contrib.auth import get_user_model

from accounts.models import UserProfile
from core.forms import StyledModelForm
from patients.models import Patient
from team.models import Professional


class UserAccountForm(forms.ModelForm):
    password = forms.CharField(label="senha temporaria", widget=forms.PasswordInput, required=False)
    role = forms.ChoiceField(label="perfil", choices=UserProfile.Role.choices)
    patient = forms.ModelChoiceField(label="paciente vinculado", queryset=Patient.objects.none(), required=False)
    professional = forms.ModelChoiceField(label="profissional vinculado", queryset=Professional.objects.none(), required=False)

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "checkbox")
            else:
                field.widget.attrs.setdefault("class", "field-control")

        self.fields["patient"].queryset = Patient.objects.filter(active=True)
        self.fields["professional"].queryset = Professional.objects.filter(active=True)

        if self.instance.pk and hasattr(self.instance, "profile"):
            profile = self.instance.profile
            self.fields["role"].initial = profile.role
            self.fields["patient"].initial = profile.patient
            self.fields["professional"].initial = profile.professional

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        patient = cleaned.get("patient")
        professional = cleaned.get("professional")

        if role == UserProfile.Role.PATIENT and not patient:
            self.add_error("patient", "Vincule um paciente para este perfil.")
        if role == UserProfile.Role.PROFESSIONAL and not professional:
            self.add_error("professional", "Vincule um profissional para este perfil.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        elif not user.pk:
            user.set_unusable_password()

        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data["role"]
            profile.patient = self.cleaned_data.get("patient")
            profile.professional = self.cleaned_data.get("professional")
            profile.save()
        return user


class UserProfileForm(StyledModelForm):
    class Meta:
        model = UserProfile
        fields = ["role", "patient", "professional", "phone"]
