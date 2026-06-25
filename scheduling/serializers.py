from rest_framework import serializers

from core.serializers import ModelCleanSerializerMixin
from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage, ServiceUsage


class AppointmentSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    professional_name = serializers.CharField(source="professional.full_name", read_only=True)

    class Meta:
        model = Appointment
        fields = "__all__"
        read_only_fields = [
            "booked_by",
            "booking_source",
            "completed_by",
            "completed_at",
            "external_provider",
            "external_event_id",
            "rescheduled_from",
            "created_at",
            "updated_at",
        ]


class ProfessionalAvailabilitySerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    professional_name = serializers.CharField(source="professional.full_name", read_only=True)

    class Meta:
        model = ProfessionalAvailability
        fields = "__all__"


class ServicePackageSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="membership.patient.full_name", read_only=True)
    plan_name = serializers.CharField(source="membership.plan.name", read_only=True)
    remaining_sessions = serializers.IntegerField(read_only=True)

    class Meta:
        model = ServicePackage
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class ServiceUsageSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="appointment.patient.full_name", read_only=True)

    class Meta:
        model = ServiceUsage
        fields = "__all__"
        read_only_fields = ["registered_by", "registered_at", "created_at", "updated_at"]
