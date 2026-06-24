from rest_framework import serializers

from accounts.models import UserProfile
from core.serializers import ModelCleanSerializerMixin


class UserProfileSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    professional_name = serializers.CharField(source="professional.full_name", read_only=True)

    class Meta:
        model = UserProfile
        fields = "__all__"
