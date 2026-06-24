from django.urls import path

from core.views import AuditLogListView, ClinicSettingsUpdateView, DashboardView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("auditoria/", AuditLogListView.as_view(), name="audit"),
    path("configuracoes/", ClinicSettingsUpdateView.as_view(), name="settings"),
]
