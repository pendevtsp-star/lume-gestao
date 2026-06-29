from django.urls import path

from checkout.views import (
    AsaasCheckoutWebhookView,
    CheckoutOrderListView,
    CheckoutPaymentEventListView,
    CheckoutStatusView,
    PatientPaymentListView,
    PatientPaymentStartView,
    PublicPlanCheckoutView,
)

app_name = "checkout"

urlpatterns = [
    path("pedidos/", CheckoutOrderListView.as_view(), name="orders"),
    path("eventos/", CheckoutPaymentEventListView.as_view(), name="events"),
    path("planos/<int:pk>/", PublicPlanCheckoutView.as_view(), name="plan"),
    path("pedido/<slug:reference>/", CheckoutStatusView.as_view(), name="status"),
    path("minhas-mensalidades/", PatientPaymentListView.as_view(), name="patient_payments"),
    path("mensalidades/<int:pk>/pagar/", PatientPaymentStartView.as_view(), name="payment_start"),
    path("webhooks/asaas/", AsaasCheckoutWebhookView.as_view(), name="asaas_webhook"),
]
