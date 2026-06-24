from django.contrib import messages
from django.db.models import Sum
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from accounts.permissions import FinanceAccessMixin
from billing.forms import ChargeForm, ExpenseCategoryForm, ExpenseForm, MembershipForm, PaymentForm, ServicePlanForm
from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.views import FormContextMixin, SearchableListView


class ServicePlanListView(FinanceAccessMixin, SearchableListView, ListView):
    model = ServicePlan
    template_name = "billing/plan_list.html"
    context_object_name = "plans"
    paginate_by = 12
    search_fields = ["name", "category", "description"]


class ServicePlanCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = ServicePlan
    form_class = ServicePlanForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:plans")
    page_title = "Plano"
    section_label = "Financeiro"
    back_url_name = "billing:plans"

    def form_valid(self, form):
        messages.success(self.request, "Plano cadastrado com sucesso.")
        return super().form_valid(form)


class ServicePlanUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = ServicePlan
    form_class = ServicePlanForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:plans")
    page_title = "Plano"
    section_label = "Financeiro"
    back_url_name = "billing:plans"

    def form_valid(self, form):
        messages.success(self.request, "Plano atualizado com sucesso.")
        return super().form_valid(form)


class MembershipListView(FinanceAccessMixin, SearchableListView, ListView):
    model = Membership
    template_name = "billing/membership_list.html"
    context_object_name = "memberships"
    paginate_by = 12
    search_fields = ["patient__full_name", "plan__name", "status"]

    def get_queryset(self):
        return super().get_queryset().select_related("patient", "plan")


class MembershipCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = Membership
    form_class = MembershipForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:memberships")
    page_title = "Mensalidade"
    section_label = "Financeiro"
    back_url_name = "billing:memberships"

    def form_valid(self, form):
        messages.success(self.request, "Mensalidade cadastrada com sucesso.")
        return super().form_valid(form)


class MembershipUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = Membership
    form_class = MembershipForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:memberships")
    page_title = "Mensalidade"
    section_label = "Financeiro"
    back_url_name = "billing:memberships"

    def form_valid(self, form):
        messages.success(self.request, "Mensalidade atualizada com sucesso.")
        return super().form_valid(form)


class PaymentListView(FinanceAccessMixin, SearchableListView, ListView):
    model = Payment
    template_name = "billing/payment_list.html"
    context_object_name = "payments"
    paginate_by = 12
    search_fields = ["membership__patient__full_name", "membership__plan__name", "status", "method"]

    def get_queryset(self):
        return super().get_queryset().select_related("membership__patient", "membership__plan")


class PaymentCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:payments")
    page_title = "Pagamento"
    section_label = "Financeiro"
    back_url_name = "billing:payments"

    def form_valid(self, form):
        messages.success(self.request, "Pagamento cadastrado com sucesso.")
        return super().form_valid(form)


class PaymentUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = Payment
    form_class = PaymentForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:payments")
    page_title = "Pagamento"
    section_label = "Financeiro"
    back_url_name = "billing:payments"

    def form_valid(self, form):
        messages.success(self.request, "Pagamento atualizado com sucesso.")
        return super().form_valid(form)


class ExpenseListView(FinanceAccessMixin, SearchableListView, ListView):
    model = Expense
    template_name = "billing/expense_list.html"
    context_object_name = "expenses"
    paginate_by = 12
    search_fields = ["description", "category__name", "status", "notes"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("category")
        status = self.request.GET.get("status", "").strip()
        kind = self.request.GET.get("kind", "").strip()
        category = self.request.GET.get("category", "").strip()
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()

        if status:
            queryset = queryset.filter(status=status)
        if kind:
            queryset = queryset.filter(kind=kind)
        if category:
            queryset = queryset.filter(category_id=category)
        if date_from:
            queryset = queryset.filter(due_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(due_date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtered = self.get_queryset()
        active_expenses = filtered.exclude(status=Expense.Status.CANCELED)
        context.update(
            {
                "status_choices": Expense.Status.choices,
                "kind_choices": Expense.Kind.choices,
                "categories": ExpenseCategory.objects.filter(active=True),
                "selected_status": self.request.GET.get("status", ""),
                "selected_kind": self.request.GET.get("kind", ""),
                "selected_category": self.request.GET.get("category", ""),
                "date_from": self.request.GET.get("date_from", ""),
                "date_to": self.request.GET.get("date_to", ""),
                "expense_total": active_expenses.aggregate(total=Sum("amount"))["total"] or 0,
                "expense_open_total": filtered.filter(status=Expense.Status.OPEN).aggregate(total=Sum("amount"))[
                    "total"
                ]
                or 0,
                "expense_paid_total": filtered.filter(status=Expense.Status.PAID).aggregate(total=Sum("amount"))[
                    "total"
                ]
                or 0,
                "expense_count": active_expenses.count(),
            }
        )
        return context


class ExpenseCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:expenses")
    page_title = "Despesa"
    section_label = "Financeiro"
    back_url_name = "billing:expenses"

    def form_valid(self, form):
        messages.success(self.request, "Despesa cadastrada com sucesso.")
        return super().form_valid(form)


class ExpenseUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:expenses")
    page_title = "Despesa"
    section_label = "Financeiro"
    back_url_name = "billing:expenses"

    def form_valid(self, form):
        messages.success(self.request, "Despesa atualizada com sucesso.")
        return super().form_valid(form)


class ExpenseCategoryListView(FinanceAccessMixin, SearchableListView, ListView):
    model = ExpenseCategory
    template_name = "billing/expense_category_list.html"
    context_object_name = "categories"
    paginate_by = 12
    search_fields = ["name", "kind"]


class ExpenseCategoryCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = ExpenseCategory
    form_class = ExpenseCategoryForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:expense_categories")
    page_title = "Categoria de despesa"
    section_label = "Financeiro"
    back_url_name = "billing:expense_categories"

    def form_valid(self, form):
        messages.success(self.request, "Categoria cadastrada com sucesso.")
        return super().form_valid(form)


class ExpenseCategoryUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = ExpenseCategory
    form_class = ExpenseCategoryForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:expense_categories")
    page_title = "Categoria de despesa"
    section_label = "Financeiro"
    back_url_name = "billing:expense_categories"

    def form_valid(self, form):
        messages.success(self.request, "Categoria atualizada com sucesso.")
        return super().form_valid(form)


class ChargeListView(FinanceAccessMixin, SearchableListView, ListView):
    model = Charge
    template_name = "billing/charge_list.html"
    context_object_name = "charges"
    paginate_by = 12
    search_fields = ["patient__full_name", "description", "status"]

    def get_queryset(self):
        return super().get_queryset().select_related("patient")


class ChargeCreateView(FormContextMixin, FinanceAccessMixin, CreateView):
    model = Charge
    form_class = ChargeForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:charges")
    page_title = "Cobranca"
    section_label = "Financeiro"
    back_url_name = "billing:charges"

    def form_valid(self, form):
        messages.success(self.request, "Cobranca cadastrada com sucesso.")
        return super().form_valid(form)


class ChargeUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = Charge
    form_class = ChargeForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:charges")
    page_title = "Cobranca"
    section_label = "Financeiro"
    back_url_name = "billing:charges"

    def form_valid(self, form):
        messages.success(self.request, "Cobranca atualizada com sucesso.")
        return super().form_valid(form)

# Create your views here.
