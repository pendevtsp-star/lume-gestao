from rest_framework.viewsets import ModelViewSet

from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from billing.serializers import (
    ChargeSerializer,
    ExpenseCategorySerializer,
    ExpenseSerializer,
    MembershipSerializer,
    PaymentSerializer,
    ServicePlanSerializer,
)
from core.api_permissions import FinanceApiPermission


class ServicePlanViewSet(ModelViewSet):
    queryset = ServicePlan.objects.all()
    serializer_class = ServicePlanSerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["active", "category"]
    search_fields = ["name", "category", "description"]
    ordering_fields = ["name", "monthly_price", "created_at"]


class MembershipViewSet(ModelViewSet):
    queryset = Membership.objects.select_related("patient", "plan")
    serializer_class = MembershipSerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["status", "plan"]
    search_fields = ["patient__full_name", "plan__name"]
    ordering_fields = ["start_date", "created_at"]


class PaymentViewSet(ModelViewSet):
    queryset = Payment.objects.select_related("membership__patient", "membership__plan")
    serializer_class = PaymentSerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["status", "method", "due_date"]
    search_fields = ["membership__patient__full_name", "membership__plan__name"]
    ordering_fields = ["due_date", "reference_month", "amount", "created_at"]


class ExpenseViewSet(ModelViewSet):
    queryset = Expense.objects.select_related("category")
    serializer_class = ExpenseSerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["status", "kind", "category", "due_date"]
    search_fields = ["description", "category__name", "notes"]
    ordering_fields = ["due_date", "amount", "created_at"]


class ExpenseCategoryViewSet(ModelViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["active", "kind"]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]


class ChargeViewSet(ModelViewSet):
    queryset = Charge.objects.select_related("patient")
    serializer_class = ChargeSerializer
    permission_classes = [FinanceApiPermission]
    filterset_fields = ["status", "due_date", "patient"]
    search_fields = ["description", "patient__full_name", "notes"]
    ordering_fields = ["due_date", "amount", "created_at"]
