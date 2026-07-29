from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core.models import WhatsAppMessageLog
from core.services.whatsapp_delivery_policy import can_retry_manually
from relationships.web.common import RelationshipAccessMixin
from scheduling.models import PatientNotification


FRIENDLY_STATUS = {
    WhatsAppMessageLog.Status.SCHEDULED: (
        "Aguardando envio",
        "A mensagem será enviada enquanto ainda fizer sentido.",
        "waiting",
    ),
    WhatsAppMessageLog.Status.SENT: (
        "Enviada",
        "Mensagem enviada com sucesso.",
        "success",
    ),
    WhatsAppMessageLog.Status.DRY_RUN: (
        "Simulada",
        "Mensagem validada no ambiente seguro.",
        "success",
    ),
    WhatsAppMessageLog.Status.FAILED: (
        "Não enviada",
        "Não foi possível enviar. Verifique a conexão e o telefone.",
        "danger",
    ),
    WhatsAppMessageLog.Status.EXPIRED: (
        "Prazo encerrado",
        "Mensagem não enviada porque o prazo terminou.",
        "muted",
    ),
    WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN: (
        "Resultado não confirmado",
        "O sistema não repetirá esta mensagem para evitar duplicidade.",
        "warning",
    ),
}

TERMINAL_MESSAGES = {
    "appointment_started": "não enviada porque o horário da sessão passou",
    "appointment_canceled": "não enviada porque a sessão foi cancelada",
    "appointment_rescheduled": "não enviada porque o horário da sessão mudou",
    "payment_settled": "não enviada porque o pagamento já foi registrado",
    "charge_settled": "não enviada porque a cobrança já foi recebida",
    "birthday_date_passed": "não enviada porque a data do aniversário passou",
    "validity_expired": "não enviada porque o prazo terminou",
    "retry_after_expiry": "não enviada porque a próxima tentativa seria tarde demais",
}


def sync_retry_notification(log):
    try:
        notification = log.delivery_notification
    except PatientNotification.DoesNotExist:
        return
    notification.status = PatientNotification.Status.PENDING
    notification.error_message = ""
    notification.save(update_fields=["status", "error_message", "updated_at"])


class RelationshipHistoryView(RelationshipAccessMixin, TemplateView):
    template_name = "relationships/history.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        entries = []
        logs = (
            WhatsAppMessageLog.objects.select_related(
                "patient",
                "appointment",
                "payment",
                "charge",
            )
            .exclude(status=WhatsAppMessageLog.Status.CANCELED)
            .order_by("-created_at")[:50]
        )
        for log in logs:
            label, detail, tone = FRIENDLY_STATUS.get(
                log.status,
                ("Atualizada", "Consulte o suporte se precisar de ajuda.", "muted"),
            )
            if log.terminal_reason in TERMINAL_MESSAGES:
                detail = TERMINAL_MESSAGES[log.terminal_reason]
            retry_decision = can_retry_manually(log, now=now)
            entries.append(
                {
                    "log": log,
                    "label": label,
                    "detail": detail,
                    "tone": tone,
                    "can_retry": (
                        log.status == WhatsAppMessageLog.Status.FAILED
                        and retry_decision.allowed
                    ),
                }
            )
        context.update(
            {
                "page_title": "Histórico de relacionamento",
                "history_entries": entries,
            }
        )
        return context


class RelationshipHistoryRetryView(RelationshipAccessMixin, View):
    def post(self, request, pk):
        log = get_object_or_404(
            WhatsAppMessageLog,
            pk=pk,
            status=WhatsAppMessageLog.Status.FAILED,
        )
        decision = can_retry_manually(log, now=timezone.now())
        if not decision.allowed:
            messages.info(request, decision.user_message)
            return redirect("relationships:history")
        now = timezone.now()
        log.status = WhatsAppMessageLog.Status.SCHEDULED
        if not log.scheduled_for:
            log.scheduled_for = now
        log.next_attempt_at = now
        log.lease_until = None
        log.attempt_count = 0
        log.error_message = ""
        log.terminal_reason = ""
        log.save(
            update_fields=[
                "status",
                "scheduled_for",
                "next_attempt_at",
                "lease_until",
                "attempt_count",
                "error_message",
                "terminal_reason",
                "updated_at",
            ]
        )
        sync_retry_notification(log)
        messages.success(request, "Mensagem recolocada na fila com segurança.")
        return redirect("relationships:history")
