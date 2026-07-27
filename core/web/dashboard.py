from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from accounts.models import UserProfile
from accounts.permissions import get_profile
from billing.models import Membership, Payment, ServicePlan
from billing.services import membership_receivables_between, month_start as membership_month_start
from core.models import ClinicSettings
from lume_connect.models import ConnectNotification, ConnectPost
from patients.models import Patient
from patients.services import patient_ids_for_professional
from scheduling.models import Appointment, ServicePackage, ServiceUsage
from team.models import Employee, Professional

WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]

def birthday_date_for_year(birth_date, year):
    try:
        return birth_date.replace(year=year)
    except ValueError:
        return birth_date.replace(year=year, day=28)


def birthday_in_period(birth_date, starts_on, ends_on):
    for year in range(starts_on.year, ends_on.year + 1):
        candidate = birthday_date_for_year(birth_date, year)
        if starts_on <= candidate <= ends_on:
            return candidate
    return None


def weekly_birthday_patients(queryset, starts_on=None, days=7):
    starts_on = starts_on or timezone.localdate()
    ends_on = starts_on + timedelta(days=days - 1)
    birthdays = []
    for patient in queryset.filter(birth_date__isnull=False).only("id", "full_name", "birth_date", "phone"):
        birthday_date = birthday_in_period(patient.birth_date, starts_on, ends_on)
        if not birthday_date:
            continue
        birthdays.append(
            {
                "patient": patient,
                "date": birthday_date,
                "display_date": birthday_date.strftime("%d/%m"),
                "weekday": "Hoje" if birthday_date == starts_on else WEEKDAY_LABELS[birthday_date.weekday()],
                "has_phone": bool(patient.phone),
            }
        )
    return sorted(birthdays, key=lambda birthday: (birthday["date"], birthday["patient"].full_name))


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
            profile and profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT, UserProfile.Role.VIEWER}
        )

        patient_queryset = Patient.objects.filter(active=True)
        if profile and profile.is_patient and profile.patient_id:
            patient_queryset = patient_queryset.filter(pk=profile.patient_id)
        elif profile and profile.is_professional and profile.professional_id:
            patient_queryset = patient_queryset.filter(pk__in=patient_ids_for_professional(profile.professional))

        pending_payments = Payment.objects.filter(status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE])
        paid_this_month = Payment.objects.filter(status=Payment.Status.PAID, paid_at__gte=month_start)
        upcoming_payment_rows = Payment.objects.filter(
            item_type=Payment.ItemType.MEMBERSHIP,
            membership__isnull=False,
            status=Payment.Status.PENDING,
            due_date__gte=today,
            due_date__lte=reminder_limit,
        ).select_related("patient", "membership__patient", "membership__plan")
        overdue_payment_rows = Payment.objects.filter(
            status__in=[Payment.Status.OVERDUE, Payment.Status.PENDING], due_date__lt=today
        ).select_related("patient", "membership__patient", "membership__plan")
        upcoming_payments = []
        overdue_payments = []
        virtual_pending_total = Decimal("0.00")
        if not finance_visible:
            pending_payments = pending_payments.none()
            paid_this_month = paid_this_month.none()
        else:
            upcoming_virtual = membership_receivables_between(today, reminder_limit)
            receivables_start = membership_month_start(today - timedelta(days=62))
            overdue_virtual = membership_receivables_between(receivables_start, today - timedelta(days=1))
            pending_virtual = membership_receivables_between(receivables_start, today)
            upcoming_payments = list(upcoming_payment_rows[:8]) + upcoming_virtual[:8]
            overdue_payments = list(overdue_payment_rows[:8]) + overdue_virtual[:8]
            upcoming_payments.sort(key=lambda payment: (payment.due_date, payment.patient_display))
            overdue_payments.sort(key=lambda payment: (payment.due_date, payment.patient_display))
            virtual_pending_total = sum((payment.amount for payment in pending_virtual), Decimal("0.00"))

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
                "birthday_patients": weekly_birthday_patients(Patient.objects.filter(active=True), today),
                "birthday_week_start": today,
                "birthday_week_end": today + timedelta(days=6),
                "birthday_whatsapp_visible": finance_visible,
                "active_patients": patient_queryset.count(),
                "active_memberships": Membership.objects.filter(status=Membership.Status.ACTIVE).count() if finance_visible else 0,
                "active_professionals": Professional.objects.filter(active=True).count() if finance_visible else 0,
                "employees": Employee.objects.filter(active=True).count() if finance_visible else 0,
                "active_plans": ServicePlan.objects.filter(active=True).count() if finance_visible else 0,
                "pending_total": (pending_payments.aggregate(total=Sum("amount"))["total"] or 0) + virtual_pending_total,
                "paid_month_total": paid_this_month.aggregate(total=Sum("amount"))["total"] or 0,
                "next_payments": pending_payments.select_related("patient", "membership__patient", "membership__plan")[:8],
                "upcoming_payments": upcoming_payments[:8],
                "overdue_payments": overdue_payments[:8],
                "next_appointments": appointment_queryset[:8],
                "reminder_days": settings.membership_due_reminder_days,
                "connect_recent_posts": (
                    ConnectPost.objects.filter(is_active=True)
                    .select_related("author", "author__profile")
                    .annotate(
                        likes_total=Count("likes", distinct=True),
                        comments_total=Count("comments", filter=Q(comments__is_active=True), distinct=True),
                    )
                    .order_by("-is_pinned", "-created_at")[:3]
                ),
                "connect_total_posts": ConnectPost.objects.filter(is_active=True).count(),
                "connect_unread_notifications": ConnectNotification.objects.filter(
                    recipient=self.request.user,
                    is_read=False,
                ).count(),
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
