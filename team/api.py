from rest_framework.viewsets import ModelViewSet

from core.api_permissions import FinanceApiPermission
from patients.services import deactivate_professional_relationships
from team.models import Employee, Professional
from team.serializers import EmployeeSerializer, ProfessionalSerializer


class EmployeeViewSet(ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["active", "role"]
    search_fields = ["full_name", "email", "phone", "role"]
    ordering_fields = ["full_name", "created_at"]

    def perform_destroy(self, instance):
        instance.active = False
        instance.full_clean()
        instance.save(update_fields=["active", "updated_at"])


class ProfessionalViewSet(ModelViewSet):
    queryset = Professional.objects.all()
    serializer_class = ProfessionalSerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["active", "specialty"]
    search_fields = ["full_name", "email", "phone", "specialty", "registration_number"]
    ordering_fields = ["full_name", "created_at"]

    def perform_update(self, serializer):
        professional = serializer.save()
        if not professional.active:
            deactivate_professional_relationships(professional)

    def perform_destroy(self, instance):
        instance.active = False
        instance.full_clean()
        instance.save(update_fields=["active", "updated_at"])
        deactivate_professional_relationships(instance)
