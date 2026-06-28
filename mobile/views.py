from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserProfile
from accounts.permissions import get_profile
from billing.models import Membership, Payment
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment, ServicePackage, ServiceUsage
from team.models import Employee, Professional


class MobileBootstrapView(APIView):
    def get(self, request):
        profile = get_profile(request.user)
        if not profile:
            return Response({"profile": None, "dashboard": {}, "features": []})

        payload = {
            "profile": self.profile_payload(profile),
            "features": self.features_for(profile, request.user.is_superuser),
            "dashboard": self.dashboard_payload(profile, request.user.is_superuser),
        }
        return Response(payload)

    def profile_payload(self, profile):
        return {
            "username": profile.user.username,
            "display_name": profile.display_name,
            "role": profile.role,
            "role_label": profile.get_role_display(),
            "avatar_url": profile.avatar_url,
            "initials": profile.initials,
            "whatsapp_number": profile.whatsapp_number,
            "whatsapp_notifications_enabled": profile.whatsapp_notifications_enabled,
        }

    def features_for(self, profile, is_superuser):
        features = ["dashboard", "agenda", "minha_conta"]
        if profile.is_patient:
            features.extend(["meu_plano", "meus_creditos"])
        if profile.is_professional:
            features.extend(["pacientes", "prontuario", "disponibilidade"])
        if is_superuser or profile.role in {
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
            UserProfile.Role.VIEWER,
        }:
            features.extend(["financeiro", "relatorios", "pacientes", "equipe"])
        if is_superuser or profile.role in {UserProfile.Role.MANAGEMENT, UserProfile.Role.VIEWER}:
            features.extend(["usuarios", "auditoria", "configuracoes"])
        return features

    def dashboard_payload(self, profile, is_superuser):
        if profile.is_patient and profile.patient_id:
            return self.patient_dashboard(profile)
        if profile.is_professional and profile.professional_id:
            return self.professional_dashboard(profile)
        if is_superuser or profile.role in {
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
            UserProfile.Role.VIEWER,
        }:
            return self.backoffice_dashboard()
        return {}

    def patient_dashboard(self, profile):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        memberships = Membership.objects.select_related("plan").filter(
            patient=profile.patient,
            status=Membership.Status.ACTIVE,
        )
        packages = ServicePackage.objects.select_related("membership__plan").filter(
            membership__patient=profile.patient,
            status=ServicePackage.Status.ACTIVE,
        )
        usages = ServiceUsage.objects.select_related("appointment__professional").filter(
            appointment__patient=profile.patient,
        )
        next_payment = (
            Payment.objects.select_related("membership__plan")
            .filter(
                membership__patient=profile.patient,
                status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
            )
            .order_by("due_date")
            .first()
        )

        weekly_allowed = sum(membership.plan.sessions_per_week for membership in memberships)
        weekly_used = (
            usages.filter(registered_at__date__gte=week_start, registered_at__date__lte=week_end).aggregate(
                total=Sum("units")
            )["total"]
            or 0
        )
        package_total = sum(package.total_sessions for package in packages)
        package_used = sum(package.used_sessions for package in packages)

        return {
            "memberships": [
                {
                    "plan": membership.plan.name,
                    "sessions_per_week": membership.plan.sessions_per_week,
                    "status": membership.status,
                }
                for membership in memberships
            ],
            "next_payment": self.payment_payload(next_payment),
            "weekly_credits": {
                "allowed": weekly_allowed,
                "used": weekly_used,
                "remaining": max(weekly_allowed - weekly_used, 0),
            },
            "package_credits": {
                "total": package_total,
                "used": package_used,
                "remaining": max(package_total - package_used, 0),
            },
            "recent_usages": [
                {
                    "date": usage.registered_at.isoformat(),
                    "professional": usage.appointment.professional.full_name,
                    "units": usage.units,
                }
                for usage in usages.order_by("-registered_at")[:8]
            ],
        }

    def payment_payload(self, payment):
        if not payment:
            return None
        return {
            "plan": payment.membership.plan.name,
            "due_date": payment.due_date.isoformat(),
            "amount": str(payment.amount),
            "status": payment.status,
        }

    def professional_dashboard(self, profile):
        today = timezone.localdate()
        assigned_patients = ProfessionalPatientAssignment.objects.filter(
            professional=profile.professional,
            active=True,
        )
        appointments = Appointment.objects.filter(
            professional=profile.professional,
            starts_at__date__gte=today,
        ).exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED])
        return {
            "assigned_patients": assigned_patients.count(),
            "upcoming_appointments": appointments.count(),
            "next_appointments": [
                {
                    "patient": appointment.patient.full_name,
                    "starts_at": appointment.starts_at.isoformat(),
                    "status": appointment.status,
                }
                for appointment in appointments.select_related("patient").order_by("starts_at")[:8]
            ],
        }

    def backoffice_dashboard(self):
        today = timezone.localdate()
        return {
            "active_patients": Patient.objects.filter(active=True).count(),
            "active_professionals": Professional.objects.filter(active=True).count(),
            "employees": Employee.objects.filter(active=True).count(),
            "upcoming_appointments": Appointment.objects.filter(starts_at__date__gte=today).exclude(
                status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED]
            ).count(),
            "pending_payments": Payment.objects.filter(
                status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE]
            ).count(),
        }
