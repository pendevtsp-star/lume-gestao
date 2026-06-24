from rest_framework.exceptions import PermissionDenied
from rest_framework.viewsets import ModelViewSet

from accounts.models import UserProfile
from accounts.permissions import get_profile
from core.api_permissions import ClinicApiPermission
from patients.models import ProfessionalPatientAssignment
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
    permission_classes = [ClinicApiPermission]
    filterset_fields = ["status", "patient", "professional", "starts_at"]
    search_fields = ["patient__full_name", "professional__full_name", "notes"]
    ordering_fields = ["starts_at", "ends_at", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        profile = get_profile(self.request.user)
        if not profile:
            return queryset.none()
        if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
            return queryset
        if profile.is_patient and profile.patient_id:
            return queryset.filter(patient=profile.patient)
        if profile.is_professional and profile.professional_id:
            return queryset.filter(professional=profile.professional)
        return queryset.none()

    def perform_create(self, serializer):
        profile = get_profile(self.request.user)
        patient = serializer.validated_data.get("patient")
        professional = serializer.validated_data.get("professional")
        if not self.request.user.is_superuser and profile:
            if profile.is_patient:
                if patient != profile.patient:
                    raise PermissionDenied("Paciente so pode agendar para si mesmo.")
                if not ProfessionalPatientAssignment.objects.filter(
                    patient=patient,
                    professional=professional,
                    active=True,
                ).exists():
                    raise PermissionDenied("Profissional nao vinculado a este paciente.")
                serializer.save(
                    booked_by=self.request.user,
                    booking_source=Appointment.BookingSource.PATIENT,
                    status=Appointment.Status.REQUESTED,
                )
                return
            if profile.is_professional:
                if professional != profile.professional:
                    raise PermissionDenied("Profissional so pode agendar na propria agenda.")
                if not ProfessionalPatientAssignment.objects.filter(
                    patient=patient,
                    professional=professional,
                    active=True,
                ).exists():
                    raise PermissionDenied("Paciente nao vinculado a este profissional.")
                serializer.save(
                    booked_by=self.request.user,
                    booking_source=Appointment.BookingSource.PROFESSIONAL,
                )
                return
            if profile.role == UserProfile.Role.MANAGEMENT:
                serializer.save(booked_by=self.request.user, booking_source=Appointment.BookingSource.MANAGEMENT)
                return
        serializer.save(booked_by=self.request.user, booking_source=Appointment.BookingSource.ADMINISTRATION)


class ProfessionalAvailabilityViewSet(ModelViewSet):
    queryset = ProfessionalAvailability.objects.select_related("professional")
    serializer_class = ProfessionalAvailabilitySerializer
    permission_classes = [ClinicApiPermission]
    filterset_fields = ["active", "professional", "weekday"]
    search_fields = ["professional__full_name", "notes"]
    ordering_fields = ["weekday", "starts_at", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        profile = get_profile(self.request.user)
        if not profile:
            return queryset.none()
        if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
            return queryset
        if profile.is_professional and profile.professional_id:
            return queryset.filter(professional=profile.professional)
        return queryset.none()

    def perform_create(self, serializer):
        profile = get_profile(self.request.user)
        professional = serializer.validated_data.get("professional")
        if profile and profile.is_professional and professional != profile.professional:
            raise PermissionDenied("Profissional so pode alterar a propria disponibilidade.")
        if profile and profile.is_patient:
            raise PermissionDenied("Paciente nao pode alterar disponibilidade.")
        serializer.save()

    def perform_update(self, serializer):
        profile = get_profile(self.request.user)
        professional = serializer.validated_data.get("professional", serializer.instance.professional)
        if profile and profile.is_professional and professional != profile.professional:
            raise PermissionDenied("Profissional so pode alterar a propria disponibilidade.")
        serializer.save()


class ServicePackageViewSet(ModelViewSet):
    queryset = ServicePackage.objects.select_related("membership__patient", "membership__plan")
    serializer_class = ServicePackageSerializer
    permission_classes = [ClinicApiPermission]
    filterset_fields = ["status", "membership"]
    search_fields = ["membership__patient__full_name", "membership__plan__name"]
    ordering_fields = ["starts_on", "expires_on", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        profile = get_profile(self.request.user)
        if not profile:
            return queryset.none()
        if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
            return queryset
        if profile.is_patient and profile.patient_id:
            return queryset.filter(membership__patient=profile.patient)
        if profile.is_professional and profile.professional_id:
            patient_ids = ProfessionalPatientAssignment.objects.filter(
                professional=profile.professional,
                active=True,
            ).values_list("patient_id", flat=True)
            return queryset.filter(membership__patient_id__in=patient_ids)
        return queryset.none()


class ServiceUsageViewSet(ModelViewSet):
    queryset = ServiceUsage.objects.select_related("service_package", "appointment__patient", "registered_by")
    serializer_class = ServiceUsageSerializer
    permission_classes = [ClinicApiPermission]
    filterset_fields = ["service_package", "appointment"]
    search_fields = ["appointment__patient__full_name", "appointment__professional__full_name"]
    ordering_fields = ["registered_at", "created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        profile = get_profile(self.request.user)
        if not profile:
            return queryset.none()
        if profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
            return queryset
        if profile.is_patient and profile.patient_id:
            return queryset.filter(appointment__patient=profile.patient)
        if profile.is_professional and profile.professional_id:
            return queryset.filter(appointment__professional=profile.professional)
        return queryset.none()

    def perform_create(self, serializer):
        profile = get_profile(self.request.user)
        if profile and profile.is_patient:
            raise PermissionDenied("Paciente nao pode registrar baixa de atendimento.")
        serializer.save(registered_by=self.request.user)
