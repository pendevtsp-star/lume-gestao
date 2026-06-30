from django import forms
from django.utils import timezone

from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.forms import StyledModelForm


class ServicePlanForm(StyledModelForm):
    class Meta:
        model = ServicePlan
        fields = [
            "name",
            "category",
            "plan_type",
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


class MembershipForm(StyledModelForm):
    class Meta:
        model = Membership
        fields = ["patient", "plan", "start_date", "due_day", "discount_amount", "status", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class PaymentForm(StyledModelForm):
    class Meta:
        model = Payment
        fields = ["membership", "reference_month", "due_date", "amount", "status", "method", "paid_at", "notes"]
        widgets = {
            "reference_month": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "paid_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


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
