from django.urls import path

from reports.views import ReportsExportView, ReportsView

app_name = "reports"

urlpatterns = [
    path("", ReportsView.as_view(), name="dashboard"),
    path("exportar/<str:export_format>/", ReportsExportView.as_view(), name="export"),
]
