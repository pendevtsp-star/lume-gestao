from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Charge, Payment
from core.models import GoogleCalendarIntegration, WhatsAppIntegration
from patients.models import Patient
from scheduling.models import Appointment


def operational_notifications(request):
    """Expose only actionable operational signals in the shared application chrome."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"operational_notifications": [], "operational_notifications_total": 0}

    profile = getattr(request.user, "profile", None)
    if not request.user.is_superuser and (not profile or profile.role not in {
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    }):
        return {"operational_notifications": [], "operational_notifications_total": 0}

    today = timezone.localdate()
    notifications = []

    requested_total = Appointment.objects.filter(
        status=Appointment.Status.REQUESTED,
        starts_at__date__gte=today,
    ).count()
    if requested_total:
        notifications.append(
            {
                "tone": "warning",
                "title": f"{requested_total} solicitacao(oes) de agenda",
                "detail": "Ha atendimentos aguardando confirmacao.",
                "url": f"{reverse('scheduling:appointments')}?status=requested",
            }
        )

    today_total = Appointment.objects.filter(
        starts_at__date=today,
        status__in=[Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED],
    ).count()
    if today_total:
        notifications.append(
            {
                "tone": "info",
                "title": f"{today_total} atendimento(s) hoje",
                "detail": "Confira a agenda antes do proximo atendimento.",
                "url": f"{reverse('scheduling:appointments')}?dia={today.isoformat()}",
            }
        )

    overdue_total = Payment.objects.filter(status=Payment.Status.OVERDUE).count() + Charge.objects.filter(
        status=Charge.Status.OVERDUE
    ).count()
    if overdue_total:
        notifications.append(
            {
                "tone": "danger",
                "title": f"{overdue_total} pendencia(s) financeira(s)",
                "detail": "Existem itens vencidos para acompanhar.",
                "url": f"{reverse('billing:payments')}?q=overdue",
            }
        )

    birthday_total = Patient.objects.filter(active=True, birth_date__month=today.month, birth_date__day=today.day).count()
    if birthday_total:
        notifications.append(
            {
                "tone": "success",
                "title": f"{birthday_total} aniversariante(s) hoje",
                "detail": "A comunicacao pode ser revisada na agenda da clinica.",
                "url": reverse("dashboard"),
            }
        )

    whatsapp = WhatsAppIntegration.objects.order_by("pk").first()
    google = GoogleCalendarIntegration.objects.order_by("pk").first()
    disconnected = []
    if not whatsapp or not whatsapp.is_connected:
        disconnected.append("WhatsApp")
    if not google or not google.is_connected:
        disconnected.append("Google Agenda")
    if disconnected:
        notifications.append(
            {
                "tone": "neutral",
                "title": "Integracao pede atencao",
                "detail": ", ".join(disconnected) + " nao esta pronto para operar.",
                "url": reverse("integrations"),
            }
        )

    return {
        "operational_notifications": notifications[:5],
        "operational_notifications_total": len(notifications),
    }
