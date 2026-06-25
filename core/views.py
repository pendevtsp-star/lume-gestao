from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, TemplateView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import ManagementAccessMixin, get_profile
from billing.models import Membership, Payment, ServicePlan
from core.forms import ClinicSettingsForm
from core.models import AuditLog, ClinicSettings
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment, ServicePackage, ServiceUsage
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
        settings = ClinicSettings.load()
        reminder_limit = today + timedelta(days=settings.membership_due_reminder_days)
        profile = get_profile(self.request.user)
        finance_visible = self.request.user.is_superuser or (
            profile and profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}
        )

        patient_queryset = Patient.objects.filter(active=True)
        if profile and profile.is_patient and profile.patient_id:
            patient_queryset = patient_queryset.filter(pk=profile.patient_id)
        elif profile and profile.is_professional and profile.professional_id:
            patient_ids = ProfessionalPatientAssignment.objects.filter(
                professional=profile.professional,
                active=True,
            ).values_list("patient_id", flat=True)
            patient_queryset = patient_queryset.filter(pk__in=patient_ids)

        pending_payments = Payment.objects.filter(status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE])
        paid_this_month = Payment.objects.filter(status=Payment.Status.PAID, paid_at__gte=month_start)
        upcoming_payments = Payment.objects.filter(
            status=Payment.Status.PENDING,
            due_date__gte=today,
            due_date__lte=reminder_limit,
        )
        overdue_payments = Payment.objects.filter(status__in=[Payment.Status.OVERDUE, Payment.Status.PENDING], due_date__lt=today)
        if not finance_visible:
            pending_payments = pending_payments.none()
            paid_this_month = paid_this_month.none()
            upcoming_payments = upcoming_payments.none()
            overdue_payments = overdue_payments.none()

        appointment_queryset = (
            Appointment.objects.select_related("patient", "professional")
            .filter(starts_at__date__gte=today)
            .exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED])
        )
        if not self.request.user.is_superuser:
            if profile and profile.is_patient and profile.patient_id:
                appointment_queryset = appointment_queryset.filter(patient=profile.patient)
            elif profile and profile.is_professional and profile.professional_id:
                appointment_queryset = appointment_queryset.filter(professional=profile.professional)

        context.update(
            {
                "finance_visible": finance_visible,
                "active_patients": patient_queryset.count(),
                "active_memberships": Membership.objects.filter(status=Membership.Status.ACTIVE).count() if finance_visible else 0,
                "active_professionals": Professional.objects.filter(active=True).count() if finance_visible else 0,
                "employees": Employee.objects.filter(active=True).count() if finance_visible else 0,
                "active_plans": ServicePlan.objects.filter(active=True).count() if finance_visible else 0,
                "pending_total": pending_payments.aggregate(total=Sum("amount"))["total"] or 0,
                "paid_month_total": paid_this_month.aggregate(total=Sum("amount"))["total"] or 0,
                "next_payments": pending_payments.select_related("membership__patient", "membership__plan")[:8],
                "upcoming_payments": upcoming_payments.select_related("membership__patient", "membership__plan")[:8],
                "overdue_payments": overdue_payments.select_related("membership__patient", "membership__plan")[:8],
                "next_appointments": appointment_queryset[:8],
                "reminder_days": settings.membership_due_reminder_days,
            }
        )
        if profile and profile.is_patient and profile.patient_id:
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            current_memberships = (
                Membership.objects.select_related("plan")
                .filter(patient=profile.patient, status=Membership.Status.ACTIVE)
                .order_by("plan__name")
            )
            active_packages = (
                ServicePackage.objects.select_related("membership__plan")
                .filter(membership__patient=profile.patient, status=ServicePackage.Status.ACTIVE)
                .order_by("expires_on", "created_at")
            )
            service_usages = (
                ServiceUsage.objects.select_related("appointment__professional")
                .filter(appointment__patient=profile.patient)
                .order_by("-registered_at")
            )
            weekly_allowed = sum(membership.plan.sessions_per_week for membership in current_memberships)
            weekly_used = (
                service_usages.filter(registered_at__date__gte=week_start, registered_at__date__lte=week_end)
                .aggregate(total=Sum("units"))["total"]
                or 0
            )
            package_total = sum(package.total_sessions for package in active_packages)
            package_used = sum(package.used_sessions for package in active_packages)
            next_payment = (
                Payment.objects.select_related("membership__plan")
                .filter(
                    membership__patient=profile.patient,
                    status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
                )
                .order_by("due_date")
                .first()
            )
            context.update(
                {
                    "patient_dashboard": True,
                    "patient_memberships": current_memberships,
                    "patient_next_payment": next_payment,
                    "patient_weekly_allowed": weekly_allowed,
                    "patient_weekly_used": weekly_used,
                    "patient_weekly_remaining": max(weekly_allowed - weekly_used, 0),
                    "patient_package_total": package_total,
                    "patient_package_used": package_used,
                    "patient_package_remaining": max(package_total - package_used, 0),
                    "patient_recent_usages": service_usages[:8],
                }
            )
        return context


class AuditLogListView(ManagementAccessMixin, SearchableListView, ListView):
    model = AuditLog
    template_name = "core/audit_list.html"
    context_object_name = "logs"
    paginate_by = 20
    search_fields = ["actor__username", "model_name", "object_repr", "action"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("actor")
        action = self.request.GET.get("action", "").strip()
        model_name = self.request.GET.get("model", "").strip()
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        if action:
            queryset = queryset.filter(action=action)
        if model_name:
            queryset = queryset.filter(model_name=model_name)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = AuditLog.objects.all()
        filtered = self.get_queryset()
        context.update(
            {
                "action_choices": AuditLog.Action.choices,
                "model_choices": base_queryset.order_by("model_name")
                .values_list("model_name", flat=True)
                .distinct(),
                "selected_action": self.request.GET.get("action", ""),
                "selected_model": self.request.GET.get("model", ""),
                "date_from": self.request.GET.get("date_from", ""),
                "date_to": self.request.GET.get("date_to", ""),
                "audit_total": filtered.count(),
                "audit_created_total": filtered.filter(action=AuditLog.Action.CREATED).count(),
                "audit_updated_total": filtered.filter(action=AuditLog.Action.UPDATED).count(),
                "audit_deleted_total": filtered.filter(action=AuditLog.Action.DELETED).count(),
            }
        )
        return context


class ClinicSettingsUpdateView(ManagementAccessMixin, UpdateView):
    model = ClinicSettings
    form_class = ClinicSettingsForm
    template_name = "core/form.html"
    success_url = reverse_lazy("settings")

    def get_object(self, queryset=None):
        return ClinicSettings.load()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Configuracoes",
                "section_label": "Gerencia",
                "back_url": reverse("dashboard"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Configuracoes da clinica atualizadas com sucesso.")
        return super().form_valid(form)

# Create your views here.
