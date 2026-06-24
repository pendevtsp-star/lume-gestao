from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.models import UserProfile
from accounts.permissions import RoleRequiredMixin
from billing.models import Charge, Expense, Membership, Payment
from patients.models import Patient
from scheduling.models import Appointment


class ReportsView(RoleRequiredMixin, TemplateView):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]
    template_name = "reports/dashboard.html"

    def get_period(self):
        today = timezone.localdate()
        start = self.request.GET.get("start") or today.replace(day=1).isoformat()
        end = self.request.GET.get("end") or today.isoformat()
        return start, end

    def sum_amount(self, queryset):
        return queryset.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end = self.get_period()

        new_patients = Patient.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
        completed_appointments = Appointment.objects.filter(
            status=Appointment.Status.COMPLETED,
            starts_at__date__gte=start,
            starts_at__date__lte=end,
        )
        paid_payments = Payment.objects.filter(status=Payment.Status.PAID, paid_at__gte=start, paid_at__lte=end)
        expenses = Expense.objects.filter(due_date__gte=start, due_date__lte=end)
        active_expenses = expenses.exclude(status=Expense.Status.CANCELED)
        open_charges = Charge.objects.filter(status=Charge.Status.OPEN, due_date__gte=start, due_date__lte=end)
        overdue_payments = Payment.objects.filter(
            status__in=[Payment.Status.OVERDUE, Payment.Status.PENDING],
            due_date__lt=timezone.localdate(),
        )

        revenue_total = self.sum_amount(paid_payments)
        expense_total = self.sum_amount(active_expenses)
        completed_count = completed_appointments.count()
        average_ticket = revenue_total / completed_count if completed_count else Decimal("0.00")

        context.update(
            {
                "start": start,
                "end": end,
                "new_patients_count": new_patients.count(),
                "active_patients_count": Patient.objects.filter(active=True).count(),
                "completed_appointments_count": completed_count,
                "active_memberships_count": Membership.objects.filter(status=Membership.Status.ACTIVE).count(),
                "revenue_total": revenue_total,
                "expense_total": expense_total,
                "net_result": revenue_total - expense_total,
                "average_ticket": average_ticket,
                "open_charges_total": self.sum_amount(open_charges),
                "overdue_payments_total": self.sum_amount(overdue_payments),
                "patients_by_month": new_patients.annotate(month=TruncMonth("created_at"))
                .values("month")
                .annotate(total=Count("id"))
                .order_by("month"),
                "appointments_by_month": completed_appointments.annotate(month=TruncMonth("starts_at"))
                .values("month")
                .annotate(total=Count("id"))
                .order_by("month"),
                "appointments_by_professional": completed_appointments.values("professional__full_name")
                .annotate(total=Count("id"))
                .order_by("-total", "professional__full_name"),
                "revenue_by_method": paid_payments.values("method")
                .annotate(total=Sum("amount"))
                .order_by("-total"),
                "expenses_by_category": active_expenses.values("category__name", "kind")
                .annotate(total=Sum("amount"), count=Count("id"))
                .order_by("-total"),
                "top_plans": Membership.objects.filter(status=Membership.Status.ACTIVE)
                .values("plan__name")
                .annotate(total=Count("id"))
                .order_by("-total", "plan__name")[:8],
                "upcoming_payments": Payment.objects.filter(
                    status=Payment.Status.PENDING,
                    due_date__gte=timezone.localdate(),
                    due_date__lte=timezone.localdate() + timedelta(days=15),
                )
                .select_related("membership__patient", "membership__plan")
                .order_by("due_date")[:8],
            }
        )
        return context
