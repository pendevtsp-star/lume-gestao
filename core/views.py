from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from billing.models import Membership, Payment, ServicePlan
from patients.models import Patient
from team.models import Employee, Professional


class SearchableListView(LoginRequiredMixin):
    search_fields = []

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if not query:
            return queryset

        filters = Q()
        for field in self.search_fields:
            filters |= Q(**{f"{field}__icontains": query})
        return queryset.filter(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        return context


class FormContextMixin:
    page_title = ""
    section_label = ""
    back_url_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["section_label"] = self.section_label
        context["back_url"] = reverse(self.back_url_name)
        return context


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month_start = today.replace(day=1)

        pending_payments = Payment.objects.filter(status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE])
        paid_this_month = Payment.objects.filter(status=Payment.Status.PAID, paid_at__gte=month_start)

        context.update(
            {
                "active_patients": Patient.objects.filter(active=True).count(),
                "active_memberships": Membership.objects.filter(status=Membership.Status.ACTIVE).count(),
                "active_professionals": Professional.objects.filter(active=True).count(),
                "employees": Employee.objects.filter(active=True).count(),
                "active_plans": ServicePlan.objects.filter(active=True).count(),
                "pending_total": pending_payments.aggregate(total=Sum("amount"))["total"] or 0,
                "paid_month_total": paid_this_month.aggregate(total=Sum("amount"))["total"] or 0,
                "next_payments": pending_payments.select_related("membership__patient", "membership__plan")[:8],
            }
        )
        return context

# Create your views here.
