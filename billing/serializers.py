from rest_framework import serializers

from billing.models import Charge, Expense, Membership, Payment, ServicePlan
from core.serializers import ModelCleanSerializerMixin


class ServicePlanSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = ServicePlan
        fields = "__all__"


class MembershipSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    monthly_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = Membership
        fields = "__all__"


class PaymentSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="membership.patient.full_name", read_only=True)
    plan_name = serializers.CharField(source="membership.plan.name", read_only=True)

    class Meta:
        model = Payment
        fields = "__all__"


class ExpenseSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = "__all__"


class ChargeSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)

    class Meta:
        model = Charge
        fields = "__all__"
