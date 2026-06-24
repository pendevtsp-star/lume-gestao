from django.urls import path

from patients.views import PatientCreateView, PatientListView, PatientUpdateView

app_name = "patients"

urlpatterns = [
    path("", PatientListView.as_view(), name="list"),
    path("novo/", PatientCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", PatientUpdateView.as_view(), name="update"),
]
