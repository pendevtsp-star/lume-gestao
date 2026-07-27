import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import WhatsAppAutomationRule, WhatsAppMessageLog, WhatsAppMessageTemplate


TOKEN_DETAILS = {
    "[Paciente]": ("Nome do paciente", "Maria Clara"),
    "[Profissional]": ("Profissional responsavel", "Dra. Helena"),
    "[Data]": ("Data da sessao", "24/07/2026"),
    "[Horario]": ("Horario da sessao", "09:00"),
    "[Clinica]": ("Nome da clinica", "Lume Studio"),
    "[TelefoneClinica]": ("Telefone da clinica", "(82) 99999-0000"),
    "[Valor]": ("Valor da cobranca", "R$ 230,00"),
    "[DataVencimento]": ("Data de vencimento", "25/07/2026"),
}

TOKEN_PATTERN = re.compile(r"\[[^\[\]]+\]")


def allowed_template_tokens(template_type):
    try:
        return WhatsAppMessageTemplate.default_config_for(template_type)["tokens"]
    except KeyError:
        return WhatsAppMessageTemplate.default_config_for(
            WhatsAppMessageTemplate.TemplateType.CUSTOM
        )["tokens"]


def validate_template_body(template_type, body):
    body = (body or "").strip()
    if body.count("[") != body.count("]"):
        raise ValidationError(
            "Revise os colchetes das variaveis. Cada marcador deve seguir o formato [Paciente]."
        )

    allowed = set(allowed_template_tokens(template_type))
    unknown = sorted(set(TOKEN_PATTERN.findall(body)) - allowed)
    if unknown:
        raise ValidationError(
            "Variavel nao disponivel para este modelo: "
            f"{', '.join(unknown)}. Use apenas os marcadores documentados abaixo."
        )
    return body


def template_variable_documentation(template_type):
    return [
        {
            "token": token,
            "description": TOKEN_DETAILS[token][0],
            "example": TOKEN_DETAILS[token][1],
        }
        for token in allowed_template_tokens(template_type)
    ]


def render_template_preview(body, template_type):
    preview = body or ""
    for item in template_variable_documentation(template_type):
        preview = preview.replace(item["token"], item["example"])
    return preview


def whatsapp_web_connection_state(gateway_status, *, enabled):
    gateway_status = gateway_status or {}
    if not enabled:
        return {
            "code": "disconnected",
            "label": "Desconectado",
            "title": "WhatsApp Web desconectado",
            "detail": "Ative a conexao para gerar um novo QR Code.",
            "show_qr": False,
            "recoverable": True,
        }

    if gateway_status.get("ready"):
        return {
            "code": "connected",
            "label": "Conectado",
            "title": "WhatsApp conectado",
            "detail": "A sessao esta pronta para os envios e automacoes da clinica.",
            "show_qr": False,
            "recoverable": True,
        }

    if gateway_status.get("qrDataUrl") or gateway_status.get("hasQr"):
        return {
            "code": "qr_ready",
            "label": "QR disponivel",
            "title": "Escaneie o QR Code",
            "detail": "Abra os aparelhos conectados no WhatsApp Business e leia o codigo.",
            "show_qr": True,
            "recoverable": True,
        }

    error = gateway_status.get("error") or gateway_status.get("lastError")
    if gateway_status.get("ok") is False or error:
        return {
            "code": "error",
            "label": "Precisa de atencao",
            "title": "Nao foi possivel preparar o WhatsApp",
            "detail": error or "O gateway nao respondeu. Gere um novo QR e tente novamente.",
            "show_qr": False,
            "recoverable": True,
        }

    return {
        "code": "preparing",
        "label": "Conectando",
        "title": "Preparando QR Code",
        "detail": "Aguarde alguns segundos enquanto a sessao e iniciada.",
        "show_qr": False,
        "recoverable": True,
    }


def _next_rule_execution(rule, now):
    if rule.trigger != WhatsAppAutomationRule.Trigger.APPOINTMENT_BEFORE:
        return None

    from scheduling.models import Appointment

    minimum_start = now + timedelta(hours=rule.hours_before)
    appointment = (
        Appointment.objects.filter(
            status__in=[Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED],
            patient__active=True,
            patient__phone__gt="",
            starts_at__gte=minimum_start,
        )
        .order_by("starts_at")
        .first()
    )
    if not appointment:
        return None
    return appointment.starts_at - timedelta(hours=rule.hours_before)


def automation_rule_operational_states(rules, *, now=None):
    now = now or timezone.now()
    states = []
    for rule in rules:
        logs = WhatsAppMessageLog.objects.filter(template=rule.template)
        last_sent = (
            logs.filter(
                status__in=[WhatsAppMessageLog.Status.SENT, WhatsAppMessageLog.Status.DRY_RUN]
            )
            .order_by("-sent_at", "-updated_at")
            .first()
        )
        recent_failures = logs.filter(
            status=WhatsAppMessageLog.Status.FAILED,
            created_at__gte=now - timedelta(days=7),
        )
        next_retry = (
            recent_failures.filter(next_attempt_at__gte=now)
            .order_by("next_attempt_at")
            .first()
        )

        if not rule.active:
            code, label, detail = "paused", "Pausada", "A regra nao cria novos envios."
        elif not rule.template.active:
            code, label, detail = (
                "template_paused",
                "Modelo pausado",
                "Ative o modelo para que esta regra volte a funcionar.",
            )
        elif next_retry:
            code, label, detail = (
                "retrying",
                "Nova tentativa agendada",
                "Uma falha temporaria sera processada novamente pela fila.",
            )
        elif recent_failures.exists():
            code, label, detail = (
                "attention",
                "Verificar falhas",
                "Ha falhas recentes do modelo usado por esta regra.",
            )
        else:
            code, label, detail = "ready", "Operacional", "Regra ativa e pronta para criar envios."

        states.append(
            {
                "rule": rule,
                "code": code,
                "label": label,
                "detail": detail,
                "next_execution_at": _next_rule_execution(rule, now) if rule.active else None,
                "last_sent_at": last_sent.sent_at if last_sent else None,
                "failure_count": recent_failures.count(),
                "next_retry_at": next_retry.next_attempt_at if next_retry else None,
            }
        )
    return states
