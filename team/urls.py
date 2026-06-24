from django.urls import path

from team.views import (
    EmployeeCreateView,
    EmployeeListView,
    EmployeeUpdateView,
    ProfessionalCreateView,
    ProfessionalListView,
    ProfessionalUpdateView,
)

app_name = "team"

urlpatterns = [
    path("funcionarios/", EmployeeListView.as_view(), name="employees"),
    path("funcionarios/novo/", EmployeeCreateView.as_view(), name="employee_create"),
    path("funcionarios/<int:pk>/editar/", EmployeeUpdateView.as_view(), name="employee_update"),
    path("profissionais/", ProfessionalListView.as_view(), name="professionals"),
    path("profissionais/novo/", ProfessionalCreateView.as_view(), name="professional_create"),
    path("profissionais/<int:pk>/editar/", ProfessionalUpdateView.as_view(), name="professional_update"),
]
