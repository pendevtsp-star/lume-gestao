from django.urls import path

from scheduling.views import (
    AppointmentCompleteView,
    AppointmentCreateView,
    AppointmentListView,
    AppointmentUpdateView,
    ServicePackageCreateView,
    ServicePackageListView,
    ServicePackageUpdateView,
)

app_name = "scheduling"

urlpatterns = [
    path("", AppointmentListView.as_view(), name="appointments"),
    path("novo/", AppointmentCreateView.as_view(), name="appointment_create"),
    path("<int:pk>/editar/", AppointmentUpdateView.as_view(), name="appointment_update"),
    path("<int:pk>/baixar/", AppointmentCompleteView.as_view(), name="appointment_complete"),
    path("pacotes/", ServicePackageListView.as_view(), name="packages"),
    path("pacotes/novo/", ServicePackageCreateView.as_view(), name="package_create"),
    path("pacotes/<int:pk>/editar/", ServicePackageUpdateView.as_view(), name="package_update"),
]
