from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models.deletion import ProtectedError
from django.db.models import Case, IntegerField, Sum, When
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import CreateView, DeleteView, FormView, ListView, TemplateView, UpdateView

from accounts.permissions import FinanceAccessMixin
from billing.forms import (
    CashClosingForm,
    ChargeForm,
    ExpenseCategoryForm,
    ExpenseForm,
    MembershipForm,
    PaymentForm,
    PaymentReceiveForm,
    QuickMembershipReceiveForm,
    ServicePlanForm,
)
from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from billing.services import (
    cash_summary_for_date,
    close_cash_for_date,
    open_membership_receivables,
    receive_membership_month,
)
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
    paginate_by = None
    queue_page_size = 30
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
        query = self.request.GET.get("q", "").strip()
        virtual_receivables = open_membership_receivables(query=query)
        receivable_rows = []
        for payment in context["payments"]:
            receivable_rows.append(
                {
                    "kind": "payment",
                    "payment": payment,
                    "patient_display": payment.patient_display,
                    "phone": payment.patient.phone if payment.patient_id else payment.membership.patient.phone,
                    "item_display": payment.item_display,
                    "reference_month": payment.reference_month,
                    "due_date": payment.due_date,
                    "amount": payment.amount,
                    "status": payment.effective_status,
                    "status_display": payment.effective_status_display,
                    "days_overdue": payment.days_overdue,
                }
            )
        for receivable in virtual_receivables:
            receivable_rows.append(
                {
                    "kind": "virtual",
                    "membership": receivable.membership,
                    "patient_display": receivable.patient_display,
                    "phone": receivable.membership.patient.phone,
                    "item_display": receivable.item_display,
                    "reference_month": receivable.reference_month,
                    "due_date": receivable.due_date,
                    "amount": receivable.amount,
                    "status": receivable.status,
                    "status_display": receivable.get_status_display(),
                    "days_overdue": receivable.days_overdue,
                }
            )
        receivable_rows.sort(key=lambda row: (row["due_date"], row["patient_display"], row["item_display"]))
        paginator = Paginator(receivable_rows, self.queue_page_size)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context["quick_receive_form"] = QuickMembershipReceiveForm()
        context["receivable_rows"] = page_obj.object_list
        context["page_obj"] = page_obj
        context["paginator"] = paginator
        context["is_paginated"] = page_obj.has_other_pages()
        context["materialized_receive_count"] = sum(1 for row in receivable_rows if row["kind"] == "payment")
        context["virtual_receive_count"] = len(virtual_receivables)
        context["available_receive_count"] = len(receivable_rows)
        context["overdue_receive_count"] = sum(1 for row in receivable_rows if row["status"] == Payment.Status.OVERDUE)
        return context

    def post(self, request, *args, **kwargs):
        form = QuickMembershipReceiveForm(request.POST)
        query = request.GET.get("q", "").strip()
        redirect_url = reverse("billing:payment_quick_receive")
        if query:
            redirect_url = f"{redirect_url}?q={query}"
        if not form.is_valid():
            messages.error(request, "Nao foi possivel registrar o recebimento. Confira os dados e tente novamente.")
            return redirect(redirect_url)
        payment = receive_membership_month(
            membership=form.cleaned_data["membership"],
            reference_month=form.cleaned_data["reference_month"],
            method=form.cleaned_data["method"],
            paid_at=form.cleaned_data["paid_at"],
            notes=form.cleaned_data["notes"],
        )
        messages.success(request, f"Mensalidade de {payment.patient_display} recebida com sucesso.")
        return redirect(redirect_url)


class CashClosingView(FinanceAccessMixin, TemplateView):
    template_name = "billing/cash_closing.html"

    def get_selected_day(self):
        return parse_date(self.request.GET.get("date", "")) or timezone.localdate()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_day = self.get_selected_day()
        summary = cash_summary_for_date(selected_day)
        closing = summary["closing"]
        context.update(
            {
                "selected_day": selected_day,
                "previous_day": selected_day - timedelta(days=1),
                "next_day": selected_day + timedelta(days=1),
                "summary": summary,
                "closing": closing,
                "cash_form": CashClosingForm(instance=closing),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        selected_day = parse_date(request.POST.get("date", "")) or timezone.localdate()
        form = CashClosingForm(request.POST)
        redirect_url = f"{reverse('billing:cash_closing')}?date={selected_day.isoformat()}"
        if not form.is_valid():
            messages.error(request, "Nao foi possivel fechar o caixa. Confira os campos e tente novamente.")
            return redirect(redirect_url)
        close_cash_for_date(
            day=selected_day,
            user=request.user,
            cash_counted=form.cleaned_data["cash_counted"],
            notes=form.cleaned_data["notes"],
        )
        messages.success(request, "Caixa fechado com sucesso.")
        return redirect(redirect_url)


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


class PaymentDeleteView(FormContextMixin, FinanceAccessMixin, DeleteView):
    model = Payment
    template_name = "billing/payment_confirm_delete.html"
    success_url = reverse_lazy("billing:payments")
    page_title = "Excluir pagamento"
    section_label = "Financeiro"
    back_url_name = "billing:payments"

    def get_queryset(self):
        return Payment.objects.select_related("patient", "membership__patient", "membership__plan")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object_name"] = f"{self.object.patient_display} - {self.object.item_display}"
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        payment_name = f"{self.object.patient_display} - {self.object.item_display}"
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(
                request,
                "Nao foi possivel excluir este pagamento porque existe um pedido de checkout vinculado ao lancamento.",
            )
            return redirect(self.success_url)
        messages.success(request, f"Pagamento {payment_name} excluido definitivamente.")
        return redirect(self.success_url)


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
