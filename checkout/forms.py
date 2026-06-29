from django import forms

from core.forms import StyledForm
from patients.models import only_digits


class PublicPlanCheckoutForm(StyledForm):
    full_name = forms.CharField(label="Nome completo", max_length=180)
    cpf = forms.CharField(label="CPF", max_length=14, required=False)
    birth_date = forms.DateField(
        label="Data de nascimento",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    phone = forms.CharField(label="WhatsApp", max_length=30, required=False)
    email = forms.EmailField(label="E-mail", required=False)
    accept_terms = forms.BooleanField(
        label="Li e aceito os termos de uso, politica de privacidade e consentimento LGPD.",
        required=True,
    )

    def clean_cpf(self):
        cpf = only_digits(self.cleaned_data.get("cpf"))
        if cpf and len(cpf) != 11:
            raise forms.ValidationError("Informe um CPF com 11 digitos.")
        return cpf

    def clean_phone(self):
        return only_digits(self.cleaned_data.get("phone"))

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("email") and not cleaned.get("phone"):
            raise forms.ValidationError("Informe e-mail ou WhatsApp para receber o acesso apos a confirmacao.")
        return cleaned
