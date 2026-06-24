from rest_framework import serializers

from core.serializers import ModelCleanSerializerMixin
from patients.models import Patient


class PatientSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            "id",
            "full_name",
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
