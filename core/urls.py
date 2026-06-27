from django.urls import path

from core.views import (
    BirthdayWhatsAppSendView,
    ClinicSettingsUpdateView,
    DashboardView,
    GoogleCalendarCallbackView,
    GoogleCalendarConnectView,
    GoogleCalendarSyncView,
    HealthCheckView,
    IntegrationsView,
)
from reports.views import AuditReportView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("auditoria/", AuditReportView.as_view(), name="audit"),
    path("configuracoes/", ClinicSettingsUpdateView.as_view(), name="settings"),
    path("aniversariantes/<int:patient_pk>/whatsapp/", BirthdayWhatsAppSendView.as_view(), name="birthday_whatsapp_send"),
    path("integracoes/", IntegrationsView.as_view(), name="integrations"),
    path("integracoes/google/conectar/", GoogleCalendarConnectView.as_view(), name="integrations_google_connect"),
    path("integracoes/google/callback/", GoogleCalendarCallbackView.as_view(), name="integrations_google_callback"),
    path("integracoes/google/sincronizar/", GoogleCalendarSyncView.as_view(), name="integrations_google_sync"),
]
