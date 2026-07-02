from django.urls import path

from checkout.views import (
    AsaasCheckoutWebhookView,
    CheckoutDashboardView,
    CheckoutMerchantAccountOnboardingView,
    CheckoutOrderListView,
    CheckoutPaymentEventListView,
    CheckoutStatusView,
    PatientPaymentListView,
    PatientPaymentStartView,
    PublicPlanCheckoutView,
)

app_name = "checkout"

urlpatterns = [
    path("", CheckoutDashboardView.as_view(), name="dashboard"),
    path("conta-recebedora/", CheckoutMerchantAccountOnboardingView.as_view(), name="merchant_onboarding"),
    path("pedidos/", CheckoutOrderListView.as_view(), name="orders"),
    path("eventos/", CheckoutPaymentEventListView.as_view(), name="events"),
    path("planos/<int:pk>/", PublicPlanCheckoutView.as_view(), name="plan"),
    path("pedido/<slug:reference>/", CheckoutStatusView.as_view(), name="status"),
    path("minhas-mensalidades/", PatientPaymentListView.as_view(), name="patient_payments"),
    path("mensalidades/<int:pk>/pagar/", PatientPaymentStartView.as_view(), name="payment_start"),
    path("webhooks/asaas/", AsaasCheckoutWebhookView.as_view(), name="asaas_webhook"),
]
