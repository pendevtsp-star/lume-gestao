from django import forms

from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.forms import StyledModelForm


class ServicePlanForm(StyledModelForm):
    class Meta:
        model = ServicePlan
        fields = ["name", "category", "monthly_price", "sessions_per_week", "description", "active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


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
