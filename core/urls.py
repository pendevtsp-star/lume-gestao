from django.urls import path

from core.views import (
    BirthdayWhatsAppSendView,
    BrevoTransactionalWebhookView,
    ClinicSettingsUpdateView,
    DashboardView,
    GoogleCalendarCallbackView,
    GoogleCalendarConnectView,
    GoogleCalendarIcsFeedView,
    GoogleCalendarSyncView,
    HealthCheckView,
    IntegrationsView,
    LegalDocumentView,
    WhatsAppWebGatewayQrView,
    WhatsAppWebGatewayStatusView,
)
from reports.views import AuditReportView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("healthz/", HealthCheckView.as_view(), name="healthz"),
    path("webhooks/brevo/email/", BrevoTransactionalWebhookView.as_view(), name="brevo_email_webhook"),
    path("termos-de-uso/", LegalDocumentView.as_view(document_key="terms"), name="terms_of_use"),
    path("privacidade/", LegalDocumentView.as_view(document_key="privacy"), name="privacy_policy"),
    path("consentimento-lgpd/", LegalDocumentView.as_view(document_key="sensitive"), name="sensitive_data_consent"),
    path("auditoria/", AuditReportView.as_view(), name="audit"),
    path("configuracoes/", ClinicSettingsUpdateView.as_view(), name="settings"),
    path("aniversariantes/<int:patient_pk>/whatsapp/", BirthdayWhatsAppSendView.as_view(), name="birthday_whatsapp_send"),
    path("integracoes/", IntegrationsView.as_view(), name="integrations"),
    path("integracoes/whatsapp-web/status/", WhatsAppWebGatewayStatusView.as_view(), name="integrations_whatsapp_web_status"),
    path("integracoes/whatsapp-web/qr/", WhatsAppWebGatewayQrView.as_view(), name="integrations_whatsapp_web_qr"),
    path("integracoes/google/conectar/", GoogleCalendarConnectView.as_view(), name="integrations_google_connect"),
    path("integracoes/google/callback/", GoogleCalendarCallbackView.as_view(), name="integrations_google_callback"),
    path("integracoes/google/sincronizar/", GoogleCalendarSyncView.as_view(), name="integrations_google_sync"),
    path("integracoes/google/agenda/<str:token>.ics", GoogleCalendarIcsFeedView.as_view(), name="integrations_google_ics_feed"),
]
