from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.db.models import Case, IntegerField, Sum, When
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, FormView, ListView, TemplateView, UpdateView

from accounts.permissions import FinanceAccessMixin
from billing.forms import (
    ChargeForm,
    ExpenseCategoryForm,
    ExpenseForm,
    MembershipForm,
    PaymentAdvanceReceiveForm,
    PaymentForm,
    PaymentReceiveForm,
    ServicePlanForm,
)
from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan, add_months
from core.deletion import (
    DELETE_ACTION_DEACTIVATE,
    DELETE_ACTION_NOW,
    DeletionDecisionMixin,
    append_deletion_note,
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


def membership_due_date_for_reference(membership, reference_month):
    return reference_month.replace(day=min(membership.due_day, 28))


def next_available_membership_reference(membership, starts_on=None):
    reference = (starts_on or timezone.localdate()).replace(day=1)
    used_references = set(
        Payment.objects.filter(membership=membership).values_list("reference_month", flat=True)
    )
    while reference in used_references:
        reference = add_months(reference, 1)
    return reference


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


class CashierDayView(FinanceAccessMixin, TemplateView):
    template_name = "billing/cashier_day.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        query = self.request.GET.get("q", "").strip()
        payment_base = Payment.objects.select_related("patient", "membership__patient", "membership__plan")
        membership_base = Membership.objects.select_related("patient", "plan").filter(status=Membership.Status.ACTIVE)
        if query:
            payment_filter = (
                Q(patient__full_name__icontains=query)
                | Q(patient__phone__icontains=query)
                | Q(membership__patient__full_name__icontains=query)
                | Q(membership__patient__phone__icontains=query)
                | Q(membership__plan__name__icontains=query)
                | Q(description__icontains=query)
            )
            membership_filter = (
                Q(patient__full_name__icontains=query)
                | Q(patient__phone__icontains=query)
                | Q(patient__cpf__icontains=query)
                | Q(plan__name__icontains=query)
            )
            payment_base = payment_base.filter(payment_filter)
            membership_base = membership_base.filter(membership_filter)

        paid_today_queryset = payment_base.filter(status=Payment.Status.PAID, paid_at=today)
        overdue_queryset = payment_base.filter(
            status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
            due_date__lt=today,
        )
        next_queryset = payment_base.filter(
            status=Payment.Status.PENDING,
            due_date__gte=today,
            due_date__lte=today + timedelta(days=7),
        )
        advance_memberships = list(membership_base.order_by("patient__full_name", "plan__name")[:10])
        for membership in advance_memberships:
            membership.next_reference_month = next_available_membership_reference(membership)
            membership.next_due_date = membership_due_date_for_reference(membership, membership.next_reference_month)

        context.update(
            {
                "q": query,
                "today": today,
                "paid_today_total": paid_today_queryset.aggregate(total=Sum("amount"))["total"] or 0,
                "paid_today_count": paid_today_queryset.count(),
                "overdue_total": overdue_queryset.aggregate(total=Sum("amount"))["total"] or 0,
                "overdue_count": overdue_queryset.count(),
                "next_total": next_queryset.aggregate(total=Sum("amount"))["total"] or 0,
                "paid_today": paid_today_queryset.order_by("-updated_at")[:8],
                "overdue_payments": overdue_queryset.order_by("due_date")[:8],
                "next_payments": next_queryset.order_by("due_date")[:8],
                "advance_memberships": advance_memberships,
            }
        )
        return context


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
        advance_queryset = self.get_advance_memberships()
        advance_memberships = list(advance_queryset[:12])
        for membership in advance_memberships:
            membership.next_reference_month = next_available_membership_reference(membership)
            membership.next_due_date = membership_due_date_for_reference(membership, membership.next_reference_month)
        context["advance_memberships"] = advance_memberships
        context["advance_membership_count"] = advance_queryset.count()
        return context

    def get_advance_memberships(self):
        query = self.request.GET.get("q", "").strip()
        queryset = (
            Membership.objects.select_related("patient", "plan")
            .filter(status=Membership.Status.ACTIVE)
            .order_by("patient__full_name", "plan__name")
        )
        if query:
            queryset = queryset.filter(
                Q(patient__full_name__icontains=query)
                | Q(patient__phone__icontains=query)
                | Q(patient__cpf__icontains=query)
                | Q(plan__name__icontains=query)
            )
        return queryset


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


class PaymentDeleteView(DeletionDecisionMixin, FormContextMixin, FinanceAccessMixin, DeleteView):
    model = Payment
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("billing:payments")
    page_title = "Excluir pagamento"
    section_label = "Financeiro"
    back_url_name = "billing:payments"
    entity_label = "pagamento"
    default_delete_action = DELETE_ACTION_DEACTIVATE
    deactivate_button_label = "Cancelar pagamento"
    deactivate_explanation = "Marca o pagamento como cancelado para que ele nao componha a rotina financeira."
    delete_now_explanation = (
        "Remove definitivamente este recebimento. Use apenas para lancamentos duplicados ou criados por engano."
    )

    def get_queryset(self):
        return Payment.objects.select_related("patient", "membership__patient", "membership__plan")

    def perform_deactivate(self):
        self.object.status = Payment.Status.CANCELED
        self.object.paid_at = None
        self.object.notes = append_deletion_note(self.object.notes)
        self.object.full_clean()
        self.object.save(update_fields=["status", "paid_at", "notes", "updated_at"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_name": f"{self.object.patient_display} - {self.object.reference_month:%m/%Y}",
                "delete_explanation": (
                    "Escolha se deseja cancelar o pagamento para preservar historico ou excluir definitivamente."
                ),
            }
        )
        return context

    def get_deactivate_success_message(self):
        return "Pagamento cancelado."


class PaymentAdvanceReceiveView(FormContextMixin, FinanceAccessMixin, FormView):
    form_class = PaymentAdvanceReceiveForm
    template_name = "core/form.html"
    success_url = reverse_lazy("billing:payment_quick_receive")
    page_title = "Receber mensalidade adiantada"
    section_label = "Financeiro"
    back_url_name = "billing:payment_quick_receive"

    def dispatch(self, request, *args, **kwargs):
        self.membership = get_object_or_404(
            Membership.objects.select_related("patient", "plan"),
            pk=kwargs["membership_pk"],
            status=Membership.Status.ACTIVE,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        reference_month = next_available_membership_reference(self.membership)
        initial.update(
            {
                "reference_month": reference_month,
                "due_date": membership_due_date_for_reference(self.membership, reference_month),
                "amount": self.membership.monthly_amount,
                "method": Payment.Method.PIX,
                "paid_at": timezone.localdate(),
            }
        )
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Receber mensalidade de {self.membership.patient.full_name}"
        return context

    def form_valid(self, form):
        reference_month = form.cleaned_data["reference_month"]
        existing_payment = Payment.objects.filter(
            membership=self.membership,
            reference_month=reference_month,
        ).first()
        if existing_payment:
            if existing_payment.status in {Payment.Status.PENDING, Payment.Status.OVERDUE}:
                messages.info(self.request, "Esta mensalidade ja esta em aberto. Baixe o pagamento existente.")
                return redirect("billing:payment_receive", pk=existing_payment.pk)
            messages.error(self.request, "Ja existe pagamento lancado para essa mensalidade.")
            return redirect("billing:payment_quick_receive")

        payment = Payment(
            patient=self.membership.patient,
            membership=self.membership,
            item_type=Payment.ItemType.MEMBERSHIP,
            description=self.membership.plan.name,
            reference_month=reference_month,
            due_date=form.cleaned_data["due_date"],
            amount=form.cleaned_data["amount"],
            status=Payment.Status.PAID,
            method=form.cleaned_data["method"],
            paid_at=form.cleaned_data["paid_at"],
            notes=form.cleaned_data.get("notes", ""),
        )
        payment.full_clean()
        payment.save()
        messages.success(
            self.request,
            f"Mensalidade {payment.reference_month:%m/%Y} de {payment.patient_display} recebida com sucesso.",
        )
        return redirect("billing:payments")


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
