from django.urls import path

from reports.views import (
    AuditReportExportView,
    AuditReportView,
    ClinicAdhesionReportExportView,
    ClinicAdhesionReportView,
    FinancialReportExportView,
    FinancialReportView,
    ReportsDashboardView,
)

app_name = "reports"

urlpatterns = [
    path("", ReportsDashboardView.as_view(), name="dashboard"),
    path("financeiro/", FinancialReportView.as_view(), name="financial"),
    path("financeiro/exportar/<str:export_format>/", FinancialReportExportView.as_view(), name="financial_export"),
    path("adesao-clinica/", ClinicAdhesionReportView.as_view(), name="clinic"),
    path(
        "adesao-clinica/exportar/<str:export_format>/",
        ClinicAdhesionReportExportView.as_view(),
        name="clinic_export",
    ),
    path("auditoria/", AuditReportView.as_view(), name="audit"),
    path("auditoria/exportar/<str:export_format>/", AuditReportExportView.as_view(), name="audit_export"),
    path("exportar/<str:export_format>/", FinancialReportExportView.as_view(), name="export"),
]
