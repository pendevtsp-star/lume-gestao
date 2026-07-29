from datetime import timedelta

from django.utils import timezone
from django.views.generic import TemplateView

from billing.models import Charge, Payment
from core.integrations.whatsapp import whatsapp_web_gateway_status
from core.models import WhatsAppIntegration, WhatsAppMessageLog
from patients.models import Patient
from relationships.web.common import RelationshipAccessMixin
from scheduling.models import Appointment


class RelationshipOverviewView(RelationshipAccessMixin, TemplateView):
    template_name = "relationships/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        today = timezone.localdate(now)
        gateway = whatsapp_web_gateway_status()
        logs = WhatsAppMessageLog.objects.exclude(
            status=WhatsAppMessageLog.Status.CANCELED
        )
        upcoming_appointments = (
            Appointment.objects.select_related("patient", "professional")
            .filter(
                status=Appointment.Status.SCHEDULED,
                starts_at__gt=now,
                starts_at__lte=now + timedelta(hours=24),
            )
            .order_by("starts_at")[:6]
        )
        birthdays = Patient.objects.filter(
            active=True,
            birth_date__month=today.month,
            birth_date__day=today.day,
        ).order_by("full_name")[:8]
        pending_payments = Payment.objects.filter(
            status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
            due_date__lte=today,
        ).count()
        pending_charges = Charge.objects.filter(
            status__in=[Charge.Status.OPEN, Charge.Status.OVERDUE],
            due_date__lt=today,
        ).count()

        context.update(
            {
                "page_title": "Relacionamento",
                "gateway_ready": bool(gateway.get("ready")),
                "connected_number": gateway.get("connectedNumber") or "",
                "integration_enabled": WhatsAppIntegration.load().enabled,
                "scheduled_count": logs.filter(
                    status=WhatsAppMessageLog.Status.SCHEDULED
                ).count(),
                "expired_count": logs.filter(
                    status=WhatsAppMessageLog.Status.EXPIRED
                ).count(),
                "failed_count": logs.filter(
                    status__in=[
                        WhatsAppMessageLog.Status.FAILED,
                        WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN,
                    ]
                ).count(),
                "upcoming_appointments": upcoming_appointments,
                "birthdays": birthdays,
                "financial_eligible_count": pending_payments + pending_charges,
            }
        )
        return context
