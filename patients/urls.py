from django.urls import path

from patients.views import (
    AssignmentCreateView,
    AssignmentListView,
    AssignmentUpdateView,
    PatientCreateView,
    PatientListView,
    PatientUpdateView,
    ProfessionalNoteCreateView,
    ProfessionalNoteListView,
)

app_name = "patients"

urlpatterns = [
    path("", PatientListView.as_view(), name="list"),
    path("novo/", PatientCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", PatientUpdateView.as_view(), name="update"),
    path("vinculos/", AssignmentListView.as_view(), name="assignments"),
    path("vinculos/novo/", AssignmentCreateView.as_view(), name="assignment_create"),
    path("vinculos/<int:pk>/editar/", AssignmentUpdateView.as_view(), name="assignment_update"),
    path("anotacoes/", ProfessionalNoteListView.as_view(), name="notes"),
    path("anotacoes/nova/", ProfessionalNoteCreateView.as_view(), name="note_create"),
]
