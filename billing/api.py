from rest_framework.viewsets import ModelViewSet

from billing.models import Charge, Expense, Membership, Payment, ServicePlan
from billing.serializers import (
    ChargeSerializer,
    ExpenseSerializer,
    MembershipSerializer,
    PaymentSerializer,
    ServicePlanSerializer,
)


class ServicePlanViewSet(ModelViewSet):
    queryset = ServicePlan.objects.all()
    serializer_class = ServicePlanSerializer
    filterset_fields = ["active", "category"]
    search_fields = ["name", "category", "description"]
    ordering_fields = ["name", "monthly_price", "created_at"]


class MembershipViewSet(ModelViewSet):
    queryset = Membership.objects.select_related("patient", "plan")
    serializer_class = MembershipSerializer
    filterset_fields = ["status", "plan"]
    search_fields = ["patient__full_name", "plan__name"]
    ordering_fields = ["start_date", "created_at"]


class PaymentViewSet(ModelViewSet):
    queryset = Payment.objects.select_related("membership__patient", "membership__plan")
    serializer_class = PaymentSerializer
    filterset_fields = ["status", "method", "due_date"]
    search_fields = ["membership__patient__full_name", "membership__plan__name"]
    ordering_fields = ["due_date", "reference_month", "amount", "created_at"]


class ExpenseViewSet(ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    filterset_fields = ["status", "category", "due_date"]
    search_fields = ["description", "notes"]
    ordering_fields = ["due_date", "amount", "created_at"]


class ChargeViewSet(ModelViewSet):
    queryset = Charge.objects.select_related("patient")
    serializer_class = ChargeSerializer
    filterset_fields = ["status", "due_date", "patient"]
    search_fields = ["description", "patient__full_name", "notes"]
    ordering_fields = ["due_date", "amount", "created_at"]
