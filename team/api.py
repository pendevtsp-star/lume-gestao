from rest_framework.viewsets import ModelViewSet

from team.models import Employee, Professional
from team.serializers import EmployeeSerializer, ProfessionalSerializer


class EmployeeViewSet(ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    filterset_fields = ["active", "role"]
    search_fields = ["full_name", "email", "phone", "role"]
    ordering_fields = ["full_name", "created_at"]


class ProfessionalViewSet(ModelViewSet):
    queryset = Professional.objects.all()
    serializer_class = ProfessionalSerializer
    filterset_fields = ["active", "specialty"]
    search_fields = ["full_name", "email", "phone", "specialty", "registration_number"]
    ordering_fields = ["full_name", "created_at"]
