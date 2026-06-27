from django.urls import path

from scheduling.views import (
    AgendaSettingsUpdateView,
    AppointmentCompleteView,
    AppointmentCancelView,
    AppointmentCalendarExportView,
    AppointmentConfirmView,
    AppointmentCreateView,
    AppointmentListView,
    AppointmentRescheduleView,
    AppointmentUpdateView,
    ProfessionalAvailabilityCreateView,
    ProfessionalAvailabilityListView,
    ProfessionalAvailabilityUpdateView,
    ServicePackageCreateView,
    ServicePackageDeleteView,
    ServicePackageListView,
    ServicePackageUpdateView,
)

app_name = "scheduling"

urlpatterns = [
    path("", AppointmentListView.as_view(), name="appointments"),
    path("configuracoes/", AgendaSettingsUpdateView.as_view(), name="agenda_settings"),
    path("google/ical/", AppointmentCalendarExportView.as_view(), name="appointments_ical"),
    path("novo/", AppointmentCreateView.as_view(), name="appointment_create"),
    path("<int:pk>/confirmar/", AppointmentConfirmView.as_view(), name="appointment_confirm"),
    path("<int:pk>/editar/", AppointmentUpdateView.as_view(), name="appointment_update"),
    path("<int:pk>/reagendar/", AppointmentRescheduleView.as_view(), name="appointment_reschedule"),
    path("<int:pk>/cancelar/", AppointmentCancelView.as_view(), name="appointment_cancel"),
    path("<int:pk>/baixar/", AppointmentCompleteView.as_view(), name="appointment_complete"),
    path("disponibilidades/", ProfessionalAvailabilityListView.as_view(), name="availabilities"),
    path("disponibilidades/nova/", ProfessionalAvailabilityCreateView.as_view(), name="availability_create"),
    path("disponibilidades/<int:pk>/editar/", ProfessionalAvailabilityUpdateView.as_view(), name="availability_update"),
    path("pacotes/", ServicePackageListView.as_view(), name="packages"),
    path("pacotes/novo/", ServicePackageCreateView.as_view(), name="package_create"),
    path("pacotes/<int:pk>/editar/", ServicePackageUpdateView.as_view(), name="package_update"),
    path("pacotes/<int:pk>/excluir/", ServicePackageDeleteView.as_view(), name="package_delete"),
]
