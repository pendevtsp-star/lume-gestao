from rest_framework.viewsets import ModelViewSet

from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment
from patients.serializers import (
    PatientSerializer,
    ProfessionalNoteSerializer,
    ProfessionalPatientAssignmentSerializer,
)


class PatientViewSet(ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    filterset_fields = ["active"]
    search_fields = ["full_name", "cpf", "phone", "email"]
    ordering_fields = ["full_name", "created_at"]


class ProfessionalPatientAssignmentViewSet(ModelViewSet):
    queryset = ProfessionalPatientAssignment.objects.select_related("patient", "professional")
    serializer_class = ProfessionalPatientAssignmentSerializer
    filterset_fields = ["active", "patient", "professional"]
    search_fields = ["patient__full_name", "professional__full_name", "notes"]
    ordering_fields = ["created_at", "updated_at"]


class ProfessionalNoteViewSet(ModelViewSet):
    queryset = ProfessionalNote.objects.select_related("patient", "professional")
    serializer_class = ProfessionalNoteSerializer
    filterset_fields = ["patient", "professional"]
    search_fields = ["patient__full_name", "professional__full_name", "title", "body"]
    ordering_fields = ["created_at", "updated_at"]
