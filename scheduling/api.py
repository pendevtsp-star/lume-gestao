from rest_framework.viewsets import ModelViewSet

from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage, ServiceUsage
from scheduling.serializers import (
    AppointmentSerializer,
    ProfessionalAvailabilitySerializer,
    ServicePackageSerializer,
    ServiceUsageSerializer,
)


class AppointmentViewSet(ModelViewSet):
    queryset = Appointment.objects.select_related("patient", "professional", "booked_by", "completed_by")
    serializer_class = AppointmentSerializer
    filterset_fields = ["status", "patient", "professional", "starts_at"]
    search_fields = ["patient__full_name", "professional__full_name", "notes"]
    ordering_fields = ["starts_at", "ends_at", "created_at"]


class ProfessionalAvailabilityViewSet(ModelViewSet):
    queryset = ProfessionalAvailability.objects.select_related("professional")
    serializer_class = ProfessionalAvailabilitySerializer
    filterset_fields = ["active", "professional", "weekday"]
    search_fields = ["professional__full_name", "notes"]
    ordering_fields = ["weekday", "starts_at", "created_at"]


class ServicePackageViewSet(ModelViewSet):
    queryset = ServicePackage.objects.select_related("membership__patient", "membership__plan")
    serializer_class = ServicePackageSerializer
    filterset_fields = ["status", "membership"]
    search_fields = ["membership__patient__full_name", "membership__plan__name"]
    ordering_fields = ["starts_on", "expires_on", "created_at"]


class ServiceUsageViewSet(ModelViewSet):
    queryset = ServiceUsage.objects.select_related("service_package", "appointment__patient", "registered_by")
    serializer_class = ServiceUsageSerializer
    filterset_fields = ["service_package", "appointment"]
    search_fields = ["appointment__patient__full_name", "appointment__professional__full_name"]
    ordering_fields = ["registered_at", "created_at"]
