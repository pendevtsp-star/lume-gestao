from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone

from billing.models import CashClosing, Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.forms import StyledModelForm


class ServicePlanForm(StyledModelForm):
    class Meta:
        model = ServicePlan
        fields = [
            "name",
            "category",
            "plan_type",
            "delivery_mode",
            "grants_homecare_access",
            "monthly_price",
            "duration_months",
            "sessions_per_week",
            "included_sessions",
            "description",
            "public_description",
            "show_on_website",
            "display_order",
            "highlight_badge",
            "active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "public_description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["monthly_price"].help_text = "Valor cobrado pelo ciclo configurado: mensal, trimestral, semestral ou avulso."
        self.fields["duration_months"].help_text = "Use 1 para mensal, 3 para trimestral, 6 para semestral ou outro ciclo em meses."
        self.fields["included_sessions"].help_text = "Total de atendimentos liberados automaticamente quando este plano/servico for atribuido ao paciente."
        self.fields["sessions_per_week"].help_text = "Referencia operacional para agenda e relatorios. Em servico avulso, mantenha 1."
        self.fields[
            "grants_homecare_access"
        ].help_text = (
            "Libera automaticamente o acesso do paciente ao modulo Lume em Casa enquanto o vinculo/plano estiver ativo. "
            "Alterar este campo afeta imediatamente todos os pacientes com vinculo ativo neste plano."
        )


class MembershipForm(StyledModelForm):
    class Meta:
        model = Membership
        fields = ["patient", "plan", "start_date", "due_day", "discount_amount", "status", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class PaymentForm(StyledModelForm):
    MONTH_CHOICES = [
        (1, "Janeiro"),
        (2, "Fevereiro"),
        (3, "Marco"),
        (4, "Abril"),
        (5, "Maio"),
        (6, "Junho"),
        (7, "Julho"),
        (8, "Agosto"),
        (9, "Setembro"),
        (10, "Outubro"),
        (11, "Novembro"),
        (12, "Dezembro"),
    ]

    reference_month_number = forms.ChoiceField(label="Mes de referencia", choices=MONTH_CHOICES)
    reference_year = forms.IntegerField(label="Ano de referencia", min_value=2020, max_value=2100)
    amount = forms.CharField(
        label="Valor",
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "R$ 0,00"}),
        help_text="Informe em reais. Ex.: 150,00 ou R$ 1.200,00.",
    )

    class Meta:
        model = Payment
        fields = [
            "patient",
            "item_type",
            "description",
            "membership",
            "reference_month_number",
            "reference_year",
            "due_date",
            "amount",
            "status",
            "method",
            "paid_at",
            "notes",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "paid_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reference = self.instance.reference_month or timezone.localdate().replace(day=1)
        if self.instance.pk and self.instance.amount is not None:
            self.fields["amount"].initial = f"{self.instance.amount:.2f}".replace(".", ",")
        if self.instance.membership_id and not self.instance.patient_id:
            self.fields["patient"].initial = self.instance.membership.patient_id
        self.fields["reference_month_number"].initial = reference.month
        self.fields["reference_year"].initial = reference.year
        self.fields["patient"].label = "Paciente/usuario"
        self.fields["item_type"].label = "Item/referencia"
        self.fields["description"].label = "Descricao do item/referencia"
        self.fields["membership"].label = "Mensalidade vinculada"
        self.fields["membership"].required = False
        self.fields["description"].required = False
        self.fields["patient"].queryset = self.fields["patient"].queryset.filter(active=True)
        self.fields["membership"].queryset = self.fields["membership"].queryset.select_related("patient", "plan").filter(
            status__in=[Membership.Status.ACTIVE, Membership.Status.PAUSED]
        )
        self.fields["patient"].help_text = "Obrigatorio para pagamentos avulsos. Em mensalidades, pode ser preenchido automaticamente pela mensalidade escolhida."
        self.fields["item_type"].help_text = "Use Mensalidade para plano ativo ou escolha servico/sessao/outro para pagamento avulso."
        self.fields["description"].help_text = "Ex.: Massagem avulsa, sessao experimental, produto ou ajuste financeiro."
        self.fields["membership"].help_text = "Obrigatorio apenas quando o item/referencia for Mensalidade."
        self.fields["reference_month_number"].help_text = "O sistema salva automaticamente como primeiro dia do mes."
        self.fields["reference_year"].help_text = "Use o ano da mensalidade, por exemplo 2026."

    def clean_amount(self):
        raw_value = str(self.cleaned_data.get("amount") or "").strip()
        normalized = raw_value.replace("R$", "").replace(" ", "")
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        try:
            return Decimal(normalized)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Informe um valor valido em reais. Ex.: 150,00.")

    def clean(self):
        cleaned_data = super().clean()
        item_type = cleaned_data.get("item_type")
        membership = cleaned_data.get("membership")
        patient = cleaned_data.get("patient")
        month = cleaned_data.get("reference_month_number")
        year = cleaned_data.get("reference_year")
        if membership:
            cleaned_data["patient"] = membership.patient
            self.instance.patient = membership.patient
            if patient and membership.patient_id != patient.pk:
                self.add_error("membership", "A mensalidade escolhida pertence a outro paciente.")
        if item_type == Payment.ItemType.MEMBERSHIP and not membership:
            self.add_error("membership", "Selecione a mensalidade vinculada.")
        if item_type != Payment.ItemType.MEMBERSHIP and not patient:
            self.add_error("patient", "Selecione o paciente para pagamento avulso.")
        if item_type != Payment.ItemType.MEMBERSHIP and not cleaned_data.get("description"):
            self.add_error("description", "Informe uma descricao para o pagamento avulso.")
        if month and year:
            reference_month = date(int(year), int(month), 1)
            cleaned_data["reference_month"] = reference_month
            self.instance.reference_month = reference_month
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        reference_month = self.cleaned_data.get("reference_month")
        if reference_month:
            instance.reference_month = reference_month
        if instance.membership_id and not instance.patient_id:
            instance.patient = instance.membership.patient
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class PaymentReceiveForm(StyledModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "method", "paid_at", "notes"]
        widgets = {
            "paid_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].label = "Valor recebido"
        self.fields["paid_at"].label = "Recebido em"
        self.fields["paid_at"].initial = self.initial.get("paid_at") or timezone.localdate()
        self.fields["method"].initial = self.initial.get("method") or Payment.Method.PIX
        self.fields["notes"].help_text = "Opcional. Use para registrar recibo, caixa ou detalhe do recebimento presencial."

    def clean(self):
        cleaned_data = super().clean()
        self.instance.status = Payment.Status.PAID
        return cleaned_data


class QuickMembershipReceiveForm(forms.Form):
    membership = forms.ModelChoiceField(queryset=Membership.objects.none(), widget=forms.HiddenInput)
    reference_month = forms.DateField(widget=forms.HiddenInput)
    method = forms.ChoiceField(label="Metodo", choices=Payment.Method.choices)
    paid_at = forms.DateField(label="Recebido em", widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(
        label="Observacao",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Opcional"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["membership"].queryset = Membership.objects.select_related("patient", "plan").filter(
            status=Membership.Status.ACTIVE
        )
        self.fields["method"].initial = Payment.Method.PIX
        self.fields["paid_at"].initial = timezone.localdate()

    def clean_reference_month(self):
        reference_month = self.cleaned_data["reference_month"]
        if reference_month.day != 1:
            raise forms.ValidationError("A referencia precisa ser o primeiro dia do mes.")
        return reference_month


class CashClosingForm(StyledModelForm):
    class Meta:
        model = CashClosing
        fields = ["cash_counted", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cash_counted"].label = "Dinheiro conferido no caixa"
        self.fields["cash_counted"].required = False
        self.fields["notes"].label = "Observacao do fechamento"
        self.fields["notes"].required = False


class ExpenseForm(StyledModelForm):
    class Meta:
        model = Expense
        fields = ["description", "category", "kind", "amount", "due_date", "paid_at", "status", "notes"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "paid_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class ExpenseCategoryForm(StyledModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "kind", "active"]


class ChargeForm(StyledModelForm):
    class Meta:
        model = Charge
        fields = ["patient", "description", "due_date", "amount", "status", "received_at", "notes"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "received_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
