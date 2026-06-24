from django.urls import path

from billing.views import (
    ChargeCreateView,
    ChargeListView,
    ChargeUpdateView,
    ExpenseCreateView,
    ExpenseListView,
    ExpenseUpdateView,
    MembershipCreateView,
    MembershipListView,
    MembershipUpdateView,
    PaymentCreateView,
    PaymentListView,
    PaymentUpdateView,
    ServicePlanCreateView,
    ServicePlanListView,
    ServicePlanUpdateView,
)

app_name = "billing"

urlpatterns = [
    path("planos/", ServicePlanListView.as_view(), name="plans"),
    path("planos/novo/", ServicePlanCreateView.as_view(), name="plan_create"),
    path("planos/<int:pk>/editar/", ServicePlanUpdateView.as_view(), name="plan_update"),
    path("mensalidades/", MembershipListView.as_view(), name="memberships"),
    path("mensalidades/nova/", MembershipCreateView.as_view(), name="membership_create"),
    path("mensalidades/<int:pk>/editar/", MembershipUpdateView.as_view(), name="membership_update"),
    path("pagamentos/", PaymentListView.as_view(), name="payments"),
    path("pagamentos/novo/", PaymentCreateView.as_view(), name="payment_create"),
    path("pagamentos/<int:pk>/editar/", PaymentUpdateView.as_view(), name="payment_update"),
    path("despesas/", ExpenseListView.as_view(), name="expenses"),
    path("despesas/nova/", ExpenseCreateView.as_view(), name="expense_create"),
    path("despesas/<int:pk>/editar/", ExpenseUpdateView.as_view(), name="expense_update"),
    path("cobrancas/", ChargeListView.as_view(), name="charges"),
    path("cobrancas/nova/", ChargeCreateView.as_view(), name="charge_create"),
    path("cobrancas/<int:pk>/editar/", ChargeUpdateView.as_view(), name="charge_update"),
]
