from rest_framework.exceptions import PermissionDenied
from rest_framework.viewsets import ModelViewSet

from accounts.models import UserProfile
from accounts.permissions import get_profile
from core.api_permissions import ClinicApiPermission, FinanceApiPermission, ProfessionalApiPermission
from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment
from patients.serializers import (
    PatientSerializer,
    ProfessionalNoteSerializer,
    ProfessionalPatientAssignmentSerializer,
)
from patients.views import patients_for_user


class PatientViewSet(ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [ClinicApiPermission]
    filterset_fields = ["active"]
    search_fields = ["full_name", "cpf", "phone", "email"]
    ordering_fields = ["full_name", "created_at"]

    def get_queryset(self):
        return patients_for_user(self.request.user)

    def require_administration(self):
        if self.request.user.is_superuser:
            return
        profile = get_profile(self.request.user)
        if not profile or profile.role not in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}:
            raise PermissionDenied("Apenas administracao ou gerencia podem alterar pacientes pela API.")

    def perform_create(self, serializer):
        self.require_administration()
        serializer.save()

    def perform_update(self, serializer):
        self.require_administration()
        serializer.save()

    def perform_destroy(self, instance):
        self.require_administration()
        instance.delete()


class ProfessionalPatientAssignmentViewSet(ModelViewSet):
    queryset = ProfessionalPatientAssignment.objects.select_related("patient", "professional")
    serializer_class = ProfessionalPatientAssignmentSerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["active", "patient", "professional"]
    search_fields = ["patient__full_name", "professional__full_name", "notes"]
    ordering_fields = ["created_at", "updated_at"]


class ProfessionalNoteViewSet(ModelViewSet):
    queryset = ProfessionalNote.objects.select_related("patient", "professional")
    serializer_class = ProfessionalNoteSerializer
    permission_classes = [ProfessionalApiPermission]
    filterset_fields = ["patient", "professional"]
    search_fields = ["patient__full_name", "professional__full_name", "title", "body"]
    ordering_fields = ["created_at", "updated_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            profile = get_profile(self.request.user)
            if profile and profile.professional_id:
                return queryset.filter(professional=profile.professional)
            return queryset.none()
        profile = get_profile(self.request.user)
        if profile and profile.is_professional and profile.professional_id:
            return queryset.filter(professional=profile.professional)
        return queryset.none()

    def perform_create(self, serializer):
        profile = get_profile(self.request.user)
        if not profile or not profile.is_professional or not profile.professional_id:
            raise PermissionDenied("Apenas profissionais podem registrar prontuario.")
        patient = serializer.validated_data.get("patient")
        if not ProfessionalPatientAssignment.objects.filter(
            patient=patient,
            professional=profile.professional,
            active=True,
        ).exists():
            raise PermissionDenied("Paciente nao vinculado a este profissional.")
        serializer.save(professional=profile.professional)

    def perform_update(self, serializer):
        profile = get_profile(self.request.user)
        if not profile or not profile.is_professional or serializer.instance.professional_id != profile.professional_id:
            raise PermissionDenied("Apenas o profissional autor pode alterar esta evolucao.")
        serializer.save(professional=profile.professional)
