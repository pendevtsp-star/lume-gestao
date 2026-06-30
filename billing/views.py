from django.contrib import messages
from django.db.models import Case, IntegerField, Sum, When
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView

from accounts.permissions import FinanceAccessMixin
from billing.forms import (
    ChargeForm,
    ExpenseCategoryForm,
    ExpenseForm,
    MembershipForm,
    PaymentForm,
    PaymentReceiveForm,
    ServicePlanForm,
)
from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.deletion import (
    DELETE_ACTION_DEACTIVATE,
    DELETE_ACTION_NOW,
    DeletionDecisionMixin,
    hard_delete_expense,
    hard_delete_membership,
    hard_delete_service_plan,
    mark_active_object_for_deletion,
    mark_expense_for_deletion,
    mark_membership_for_deletion,
    membership_has_pending_obligations,
    service_plan_has_pending_obligations,
)
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
    page_title = "Plano/Servico"
    section_label = "Financeiro"
    back_url_name = "billing:plans"

    def form_valid(self, form):
        messages.success(self.request, "Plano/servico cadastrado com sucesso.")
        return super().form_valid(form)


class ServicePlanUpdateView(FormContextMixin, FinanceAccessMixin, UpdateView):
    model = ServicePlan
    form_class = ServicePlanForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:plans")
    page_title = "Plano/Servico"
    section_label = "Financeiro"
    back_url_name = "billing:plans"

    def form_valid(self, form):
        messages.success(self.request, "Plano/servico atualizado com sucesso.")
        return super().form_valid(form)


class ServicePlanDeleteView(DeletionDecisionMixin, FormContextMixin, FinanceAccessMixin, DeleteView):
    model = ServicePlan
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("billing:plans")
    page_title = "Excluir plano/servico"
    section_label = "Financeiro"
    back_url_name = "billing:plans"
    entity_label = "plano/servico"

    def get_default_delete_action(self):
        if service_plan_has_pending_obligations(self.object):
            return DELETE_ACTION_DEACTIVATE
        return DELETE_ACTION_NOW

    def perform_delete_now(self):
        hard_delete_service_plan(self.object)

    def perform_deactivate(self):
        mark_active_object_for_deletion(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_name": self.object.name,
                "entity_label": self.entity_label,
                "delete_explanation": (
                    "Escolha se deseja deixar o plano/servico indisponivel para novas vendas ou excluir definitivamente."
                ),
            }
        )
        return context


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


class MembershipDeleteView(DeletionDecisionMixin, FormContextMixin, FinanceAccessMixin, DeleteView):
    model = Membership
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("billing:memberships")
    page_title = "Excluir mensalidade"
    section_label = "Financeiro"
    back_url_name = "billing:memberships"
    entity_label = "mensalidade"
    deactivate_button_label = "Cancelar mensalidade"
    deactivate_explanation = (
        "Cancela a mensalidade, suas cobrancas pendentes e a adesao ativa vinculada. "
        "Valores ja pagos continuam no historico financeiro."
    )

    def get_queryset(self):
        return Membership.objects.select_related("patient", "plan")

    def get_default_delete_action(self):
        if membership_has_pending_obligations(self.object):
            return DELETE_ACTION_DEACTIVATE
        return DELETE_ACTION_NOW

    def perform_delete_now(self):
        hard_delete_membership(self.object)

    def perform_deactivate(self):
        mark_membership_for_deletion(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_name": f"{self.object.patient.full_name} - {self.object.plan.name}",
                "delete_explanation": (
                    "Escolha se deseja cancelar a mensalidade para retirar da rotina financeira ou excluir definitivamente."
                ),
            }
        )
        return context


class PaymentListView(FinanceAccessMixin, SearchableListView, ListView):
    model = Payment
    template_name = "billing/payment_list.html"
    context_object_name = "payments"
    paginate_by = 12
    search_fields = [
        "patient__full_name",
        "patient__phone",
        "membership__patient__full_name",
        "membership__plan__name",
        "description",
        "item_type",
        "status",
        "method",
    ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("patient", "membership__patient", "membership__plan")
            .annotate(
                status_priority=Case(
                    When(status=Payment.Status.OVERDUE, then=0),
                    When(status=Payment.Status.PENDING, then=1),
                    default=2,
                    output_field=IntegerField(),
                )
            )
            .order_by("status_priority", "due_date", "patient__full_name", "membership__patient__full_name")
        )


class PaymentQuickReceiveView(FinanceAccessMixin, SearchableListView, ListView):
    model = Payment
    template_name = "billing/payment_quick_receive.html"
    context_object_name = "payments"
    paginate_by = 12
    search_fields = [
        "membership__patient__full_name",
        "membership__patient__phone",
        "membership__patient__cpf",
        "membership__plan__name",
    ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                item_type=Payment.ItemType.MEMBERSHIP,
                membership__isnull=False,
                status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
            )
            .select_related("patient", "membership__patient", "membership__plan")
            .annotate(
                status_priority=Case(
                    When(status=Payment.Status.OVERDUE, then=0),
                    default=1,
                    output_field=IntegerField(),
                )
            )
            .order_by("status_priority", "due_date", "patient__full_name", "membership__patient__full_name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pending_receive_count"] = context["paginator"].count if context.get("paginator") else len(context["payments"])
        return context


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


class PaymentReceiveView(FormContextMixin, FinanceAccessMixin, FormView):
    form_class = PaymentReceiveForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:payments")
    page_title = "Receber pagamento"
    section_label = "Financeiro"
    back_url_name = "billing:payments"

    def dispatch(self, request, *args, **kwargs):
        self.payment = get_object_or_404(
            Payment.objects.select_related("patient", "membership__patient", "membership__plan"),
            pk=kwargs["pk"],
        )
        if self.payment.status in {Payment.Status.PAID, Payment.Status.CANCELED}:
            messages.warning(request, "Este pagamento nao esta disponivel para baixa manual.")
            return redirect("billing:payments")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial.update(
            {
                "amount": self.payment.amount,
                "method": self.payment.method if self.payment.method != Payment.Method.MANUAL else Payment.Method.PIX,
                "paid_at": timezone.localdate(),
                "notes": self.payment.notes,
            }
        )
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.payment
        return kwargs

    def form_valid(self, form):
        payment = form.save(commit=False)
        payment.status = Payment.Status.PAID
        payment.full_clean()
        payment.save()
        messages.success(
            self.request,
            f"Pagamento de {payment.patient_display} recebido com sucesso.",
        )
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


class ExpenseDeleteView(DeletionDecisionMixin, FormContextMixin, FinanceAccessMixin, DeleteView):
    model = Expense
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("billing:expenses")
    page_title = "Excluir despesa"
    section_label = "Financeiro"
    back_url_name = "billing:expenses"
    entity_label = "despesa"
    default_delete_action = DELETE_ACTION_NOW
    deactivate_button_label = "Cancelar despesa"
    deactivate_explanation = "Marca a despesa como cancelada para que ela nao componha os relatorios financeiros."

    def perform_delete_now(self):
        hard_delete_expense(self.object)

    def perform_deactivate(self):
        mark_expense_for_deletion(self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_name": self.object.description,
                "delete_explanation": (
                    "Escolha se deseja cancelar a despesa para preservar historico ou excluir definitivamente."
                ),
            }
        )
        return context


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
