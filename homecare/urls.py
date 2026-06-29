from django.urls import path

from homecare.views import (
    HomecareAsaasWebhookView,
    HomecareCategoryCreateView,
    HomecareCategoryListView,
    HomecareCategoryUpdateView,
    HomecareDashboardView,
    HomecarePaymentEventListView,
    HomecarePlanCreateView,
    HomecarePlanListView,
    HomecarePlanUpdateView,
    HomecareSubscriptionCreateView,
    HomecareSubscriptionListView,
    HomecareSubscriptionUpdateView,
    HomecareVideoCreateView,
    HomecareVideoListView,
    HomecareVideoRetryUploadView,
    HomecareVideoUpdateView,
)

app_name = "homecare"

urlpatterns = [
    path("", HomecareDashboardView.as_view(), name="dashboard"),
    path("categorias/", HomecareCategoryListView.as_view(), name="categories"),
    path("categorias/nova/", HomecareCategoryCreateView.as_view(), name="category_create"),
    path("categorias/<int:pk>/editar/", HomecareCategoryUpdateView.as_view(), name="category_update"),
    path("planos/", HomecarePlanListView.as_view(), name="plans"),
    path("planos/novo/", HomecarePlanCreateView.as_view(), name="plan_create"),
    path("planos/<int:pk>/editar/", HomecarePlanUpdateView.as_view(), name="plan_update"),
    path("videos/", HomecareVideoListView.as_view(), name="videos"),
    path("videos/novo/", HomecareVideoCreateView.as_view(), name="video_create"),
    path("videos/<int:pk>/editar/", HomecareVideoUpdateView.as_view(), name="video_update"),
    path("videos/<int:pk>/reenviar-upload/", HomecareVideoRetryUploadView.as_view(), name="video_retry_upload"),
    path("assinaturas/", HomecareSubscriptionListView.as_view(), name="subscriptions"),
    path("assinaturas/nova/", HomecareSubscriptionCreateView.as_view(), name="subscription_create"),
    path("assinaturas/<int:pk>/editar/", HomecareSubscriptionUpdateView.as_view(), name="subscription_update"),
    path("eventos-pagamento/", HomecarePaymentEventListView.as_view(), name="payment_events"),
    path("webhooks/asaas/", HomecareAsaasWebhookView.as_view(), name="asaas_webhook"),
]
