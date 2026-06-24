from rest_framework.viewsets import ModelViewSet

from billing.models import Membership, Payment, ServicePlan
from billing.serializers import MembershipSerializer, PaymentSerializer, ServicePlanSerializer


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
