from rest_framework import serializers

from core.serializers import ModelCleanSerializerMixin
from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment


class PatientSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            "id",
            "full_name",
            "photo",
            "cpf",
            "birth_date",
            "phone",
            "email",
            "emergency_contact",
            "address",
            "clinical_notes",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class ProfessionalPatientAssignmentSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    professional_name = serializers.CharField(source="professional.full_name", read_only=True)

    class Meta:
        model = ProfessionalPatientAssignment
        fields = "__all__"


class ProfessionalNoteSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    professional_name = serializers.CharField(source="professional.full_name", read_only=True)

    class Meta:
        model = ProfessionalNote
        fields = "__all__"
