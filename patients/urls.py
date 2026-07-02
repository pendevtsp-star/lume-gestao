from django.urls import path
from django.views.generic import RedirectView

from patients.views import (
    AssignmentCreateView,
    AssignmentListView,
    AssignmentUpdateView,
    PatientCreateView,
    PatientDeleteView,
    PatientEnrollmentCreateView,
    PatientListView,
    PatientQuickPanelView,
    PatientUpdateView,
    ProfessionalNoteCreateView,
    ProfessionalNoteListView,
    ProfessionalNoteUpdateView,
    ProfessionalRecordExportView,
    ProfessionalRecordPdfPreviewView,
    ProfessionalRecordPatientListView,
)

app_name = "patients"

urlpatterns = [
    path("", PatientListView.as_view(), name="list"),
    path("novo/", PatientCreateView.as_view(), name="create"),
    path("nova-matricula/", PatientEnrollmentCreateView.as_view(), name="enrollment_create"),
    path("<int:pk>/painel/", PatientQuickPanelView.as_view(), name="quick_panel"),
    path("<int:pk>/editar/", PatientUpdateView.as_view(), name="update"),
    path("<int:pk>/excluir/", PatientDeleteView.as_view(), name="delete"),
    path("vinculos/", AssignmentListView.as_view(), name="assignments"),
    path("vinculos/novo/", AssignmentCreateView.as_view(), name="assignment_create"),
    path("vinculos/<int:pk>/editar/", AssignmentUpdateView.as_view(), name="assignment_update"),
    path("prontuario/", ProfessionalRecordPatientListView.as_view(), name="notes"),
    path("prontuario/<int:patient_pk>/", ProfessionalNoteListView.as_view(), name="patient_notes"),
    path("prontuario/<int:patient_pk>/novo/", ProfessionalNoteCreateView.as_view(), name="note_create"),
    path("prontuario/<int:patient_pk>/<int:pk>/editar/", ProfessionalNoteUpdateView.as_view(), name="note_update"),
    path(
        "prontuario/<int:patient_pk>/preview/pdf/",
        ProfessionalRecordPdfPreviewView.as_view(),
        name="note_pdf_preview",
    ),
    path(
        "prontuario/<int:patient_pk>/exportar/<str:export_format>/",
        ProfessionalRecordExportView.as_view(),
        name="note_export",
    ),
    path("anotacoes/", RedirectView.as_view(pattern_name="patients:notes", permanent=False)),
    path("anotacoes/nova/", RedirectView.as_view(pattern_name="patients:notes", permanent=False)),
]
