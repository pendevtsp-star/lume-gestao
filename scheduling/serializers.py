from rest_framework import serializers

from core.serializers import ModelCleanSerializerMixin
from scheduling.models import Appointment, ServicePackage, ServiceUsage


class AppointmentSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    professional_name = serializers.CharField(source="professional.full_name", read_only=True)

    class Meta:
        model = Appointment
        fields = "__all__"


class ServicePackageSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="membership.patient.full_name", read_only=True)
    plan_name = serializers.CharField(source="membership.plan.name", read_only=True)
    remaining_sessions = serializers.IntegerField(read_only=True)

    class Meta:
        model = ServicePackage
        fields = "__all__"


class ServiceUsageSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="appointment.patient.full_name", read_only=True)

    class Meta:
        model = ServiceUsage
        fields = "__all__"
