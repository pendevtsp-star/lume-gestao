from rest_framework import serializers

from core.serializers import ModelCleanSerializerMixin
from team.models import Employee, Professional


class EmployeeSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = "__all__"


class ProfessionalSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Professional
        fields = "__all__"
