from django import forms

from billing.models import Charge, Payment
from patients.models import Patient

from .models import FiscalDocument, FiscalSettings


class StyledFormMixin:
    def _style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "checkbox")
                continue
            widget.attrs.setdefault("class", "field-control")


class FiscalSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FiscalSettings
        fields = [
            "provider",
            "environment",
            "municipality",
            "cnpj",
            "municipal_registration",
            "tax_regime",
            "default_service_code",
            "default_iss_rate",
            "api_key",
            "nfse_enabled",
        ]
        widgets = {
            "api_key": forms.PasswordInput(render_value=True),
        }
        help_texts = {
            "api_key": "Use token/chave do provedor. Nao informe senha pessoal.",
            "default_service_code": "Ex.: codigo municipal ou item de servico informado pela prefeitura/provedor.",
            "nfse_enabled": "Ative apenas quando prefeitura/provedor estiverem configurados.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class FiscalDocumentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FiscalDocument
        fields = [
            "document_type",
            "patient",
            "payment",
            "charge",
            "issue_date",
            "description",
            "service_code",
            "amount",
            "iss_rate",
            "customer_name",
            "customer_document",
            "customer_email",
            "customer_phone",
            "notes",
        ]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "document_type": "NFS-e e documento fiscal. Cupom/recibo interno serve como comprovante, nao substitui NFS-e.",
            "service_code": "Confirme o codigo correto com a prefeitura/contador da clinica.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.filter(active=True).order_by("full_name")
        self.fields["payment"].queryset = Payment.objects.select_related("membership__patient").order_by("-due_date")
        self.fields["charge"].queryset = Charge.objects.select_related("patient").order_by("-due_date")
        self._style_fields()

    def clean(self):
        cleaned_data = super().clean()
        payment = cleaned_data.get("payment")
        charge = cleaned_data.get("charge")
        if payment and charge:
            raise forms.ValidationError("Escolha pagamento ou cobranca, nao os dois ao mesmo tempo.")
        return cleaned_data
