from django.urls import path

from reports.views import (
    AuditReportExportView,
    AuditReportPdfPreviewView,
    AuditReportView,
    ClinicAdhesionReportExportView,
    ClinicAdhesionReportPdfPreviewView,
    ClinicAdhesionReportView,
    FinancialReportExportView,
    FinancialReportPdfPreviewView,
    FinancialReportView,
    MonthlyReportExportView,
    MonthlyReportView,
    ReportsDashboardView,
)

app_name = "reports"

urlpatterns = [
    path("", ReportsDashboardView.as_view(), name="dashboard"),
    path("financeiro/", FinancialReportView.as_view(), name="financial"),
    path("financeiro/preview/pdf/", FinancialReportPdfPreviewView.as_view(), name="financial_pdf_preview"),
    path("financeiro/exportar/<str:export_format>/", FinancialReportExportView.as_view(), name="financial_export"),
    path("adesao-clinica/", ClinicAdhesionReportView.as_view(), name="clinic"),
    path("acompanhamento-mensal/", MonthlyReportView.as_view(), name="monthly"),
    path("acompanhamento-mensal/exportar/<str:export_format>/", MonthlyReportExportView.as_view(), name="monthly_export"),
    path("adesao-clinica/preview/pdf/", ClinicAdhesionReportPdfPreviewView.as_view(), name="clinic_pdf_preview"),
    path(
        "adesao-clinica/exportar/<str:export_format>/",
        ClinicAdhesionReportExportView.as_view(),
        name="clinic_export",
    ),
    path("auditoria/", AuditReportView.as_view(), name="audit"),
    path("auditoria/preview/pdf/", AuditReportPdfPreviewView.as_view(), name="audit_pdf_preview"),
    path("auditoria/exportar/<str:export_format>/", AuditReportExportView.as_view(), name="audit_export"),
    path("exportar/<str:export_format>/", FinancialReportExportView.as_view(), name="export"),
]
