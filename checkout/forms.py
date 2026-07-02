from django import forms

from checkout.models import CheckoutMerchantAccount
from core.forms import StyledForm, StyledModelForm
from patients.models import only_digits


class CheckoutMerchantAccountForm(StyledModelForm):
    postal_code = forms.CharField(label="CEP", max_length=20)

    required_fields = [
        "legal_name",
        "company_type",
        "responsible_name",
        "document",
        "monthly_income",
        "email",
        "phone",
        "address",
        "address_number",
        "neighborhood",
        "city",
        "state",
        "postal_code",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.required_fields:
            self.fields[field_name].required = True

    class Meta:
        model = CheckoutMerchantAccount
        fields = [
            "legal_name",
            "trade_name",
            "company_type",
            "responsible_name",
            "document",
            "birth_date",
            "monthly_income",
            "email",
            "phone",
            "address",
            "address_number",
            "complement",
            "neighborhood",
            "city",
            "state",
            "postal_code",
            "notes",
        ]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "legal_name": "Nome completo ou razao social que sera usado no cadastro financeiro.",
            "trade_name": "Nome de exibicao da clinica, quando existir.",
            "responsible_name": "Pessoa responsavel por acompanhar o cadastro e recebimentos.",
            "document": "Informe apenas numeros. Aceita CPF ou CNPJ.",
            "birth_date": "Obrigatoria para cadastro como pessoa fisica.",
            "monthly_income": "Estimativa mensal usada na analise do provedor.",
            "phone": "Informe o celular/WhatsApp financeiro com DDD.",
            "postal_code": "Informe apenas numeros.",
            "notes": "Observacoes internas. Nao coloque senhas, tokens ou dados de cartao.",
        }

    def clean_document(self):
        document = only_digits(self.cleaned_data.get("document"))
        if len(document) not in {11, 14}:
            raise forms.ValidationError("Informe um CPF com 11 digitos ou CNPJ com 14 digitos.")
        return document

    def clean_phone(self):
        phone = only_digits(self.cleaned_data.get("phone"))
        if len(phone) < 10:
            raise forms.ValidationError("Informe um telefone com DDD.")
        return phone

    def clean_postal_code(self):
        postal_code = only_digits(self.cleaned_data.get("postal_code"))
        if len(postal_code) != 8:
            raise forms.ValidationError("Informe um CEP com 8 digitos.")
        return postal_code

    def clean_state(self):
        state = (self.cleaned_data.get("state") or "").strip().upper()
        if len(state) != 2:
            raise forms.ValidationError("Informe a UF com 2 letras.")
        return state

    def clean_monthly_income(self):
        monthly_income = self.cleaned_data.get("monthly_income")
        if monthly_income is not None and monthly_income <= 0:
            raise forms.ValidationError("Informe um valor maior que zero.")
        return monthly_income

    def clean(self):
        cleaned = super().clean()
        document = cleaned.get("document") or ""
        if len(document) == 11 and not cleaned.get("birth_date"):
            self.add_error("birth_date", "A data de nascimento e obrigatoria para pessoa fisica.")
        return cleaned


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
