from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from billing.forms import MembershipForm, PaymentForm, ServicePlanForm
from billing.models import Membership, Payment, ServicePlan
from core.views import FormContextMixin, SearchableListView


class ServicePlanListView(SearchableListView, ListView):
    model = ServicePlan
    template_name = "billing/plan_list.html"
    context_object_name = "plans"
    paginate_by = 12
    search_fields = ["name", "category", "description"]


class ServicePlanCreateView(FormContextMixin, LoginRequiredMixin, CreateView):
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


class ServicePlanUpdateView(FormContextMixin, LoginRequiredMixin, UpdateView):
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


class MembershipListView(SearchableListView, ListView):
    model = Membership
    template_name = "billing/membership_list.html"
    context_object_name = "memberships"
    paginate_by = 12
    search_fields = ["patient__full_name", "plan__name", "status"]

    def get_queryset(self):
        return super().get_queryset().select_related("patient", "plan")


class MembershipCreateView(FormContextMixin, LoginRequiredMixin, CreateView):
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


class MembershipUpdateView(FormContextMixin, LoginRequiredMixin, UpdateView):
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


class PaymentListView(SearchableListView, ListView):
    model = Payment
    template_name = "billing/payment_list.html"
    context_object_name = "payments"
    paginate_by = 12
    search_fields = ["membership__patient__full_name", "membership__plan__name", "status", "method"]

    def get_queryset(self):
        return super().get_queryset().select_related("membership__patient", "membership__plan")


class PaymentCreateView(FormContextMixin, LoginRequiredMixin, CreateView):
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


class PaymentUpdateView(FormContextMixin, LoginRequiredMixin, UpdateView):
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

# Create your views here.
