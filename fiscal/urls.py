from django.urls import path

from . import views

app_name = "fiscal"

urlpatterns = [
    path("", views.FiscalDashboardView.as_view(), name="dashboard"),
    path("configuracoes/", views.FiscalSettingsView.as_view(), name="settings"),
    path("documentos/novo/", views.FiscalDocumentCreateView.as_view(), name="document_create"),
    path("documentos/<int:pk>/editar/", views.FiscalDocumentUpdateView.as_view(), name="document_update"),
    path("documentos/<int:pk>/emitir/", views.FiscalDocumentIssueView.as_view(), name="document_issue"),
    path("documentos/<int:pk>/preview/pdf/", views.FiscalDocumentPdfPreviewView.as_view(), name="document_pdf_preview"),
    path("documentos/<int:pk>/pdf/", views.FiscalDocumentPdfView.as_view(), name="document_pdf"),
    path("documentos/<int:pk>/email/", views.FiscalDocumentEmailView.as_view(), name="document_email"),
    path("documentos/<int:pk>/whatsapp/", views.FiscalDocumentWhatsAppView.as_view(), name="document_whatsapp"),
]
