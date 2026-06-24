from rest_framework.viewsets import ModelViewSet

from patients.models import Patient
from patients.serializers import PatientSerializer


class PatientViewSet(ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    filterset_fields = ["active"]
    search_fields = ["full_name", "cpf", "phone", "email"]
    ordering_fields = ["full_name", "created_at"]
