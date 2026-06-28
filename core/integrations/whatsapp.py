from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from core.integrations.http import IntegrationError, post_form, post_json
from core.models import WhatsAppIntegration, WhatsAppMessageLog


def normalize_whatsapp_number(number, default_country_code="55"):
    digits = "".join(character for character in str(number or "") if character.isdigit())
    if not digits:
        raise IntegrationError("Informe um numero de WhatsApp.")
    if len(digits) <= 11 and default_country_code:
        digits = f"{default_country_code}{digits}"
    return digits


def whatsapp_embedded_signup_credentials(integration=None):
    integration = integration or WhatsAppIntegration.load()
    return (
        integration.embedded_app_id or settings.WHATSAPP_EMBEDDED_APP_ID,
        integration.embedded_config_id or settings.WHATSAPP_EMBEDDED_CONFIG_ID,
        integration.embedded_app_secret or settings.WHATSAPP_EMBEDDED_APP_SECRET,
    )


def whatsapp_embedded_signup_configured(integration=None):
    return all(whatsapp_embedded_signup_credentials(integration))


def exchange_whatsapp_embedded_signup_code(code, integration=None):
    integration = integration or WhatsAppIntegration.load()
    app_id, _config_id, app_secret = whatsapp_embedded_signup_credentials(integration)
    if not all([app_id, app_secret]):
        raise IntegrationError("Configure Meta App ID, Configuration ID e App Secret antes de conectar.")
    if not code:
        raise IntegrationError("A Meta nao retornou o codigo de autorizacao.")

    token_data = post_form(
        f"https://graph.facebook.com/{settings.WHATSAPP_META_API_VERSION}/oauth/access_token",
        {
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
        },
        timeout=settings.WHATSAPP_TIMEOUT,
    )
    access_token = token_data.get("access_token")
    if not access_token:
        raise IntegrationError("A Meta nao retornou token de acesso para o WhatsApp.")
    integration.access_token = access_token
    integration.enabled = True
    integration.connected_at = timezone.now()
    integration.last_error = ""
    integration.save(update_fields=["access_token", "enabled", "connected_at", "last_error", "updated_at"])
    return token_data


def send_whatsapp_text(to_number, message, integration=None):
    integration = integration or WhatsAppIntegration.load()
    target = normalize_whatsapp_number(to_number, integration.default_country_code)
    if not integration.enabled:
        raise IntegrationError("Integracao WhatsApp esta desativada.")
    if integration.provider != WhatsAppIntegration.Provider.META:
        raise IntegrationError("Twilio esta documentado como alternativa, mas ainda nao foi ativado neste modulo.")
    if integration.dry_run or settings.WHATSAPP_DRY_RUN:
        integration.last_test_at = timezone.now()
        integration.last_error = ""
        integration.save(update_fields=["last_test_at", "last_error", "updated_at"])
        return {"dry_run": True, "to": target, "message": message}
    access_token = integration.access_token or settings.WHATSAPP_META_ACCESS_TOKEN
    if not access_token:
        raise IntegrationError("Conecte o WhatsApp pela Meta ou configure WHATSAPP_META_ACCESS_TOKEN no .env.")
    phone_number_id = integration.phone_number_id or settings.WHATSAPP_META_PHONE_NUMBER_ID
    if not phone_number_id:
        raise IntegrationError("Configure WHATSAPP_META_PHONE_NUMBER_ID ou o ID do numero na tela de integracoes.")

    url = f"https://graph.facebook.com/{settings.WHATSAPP_META_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": target,
        "type": "text",
        "text": {"body": message},
    }
    response = post_json(
        url,
        payload,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=settings.WHATSAPP_TIMEOUT,
    )
    integration.last_test_at = timezone.now()
    integration.last_error = ""
    integration.save(update_fields=["last_test_at", "last_error", "updated_at"])
    return response


def format_whatsapp_currency(value):
    amount = value if isinstance(value, Decimal) else Decimal(str(value or "0"))
    return f"R$ {amount:.2f}".replace(".", ",")


def render_whatsapp_template(message, context):
    rendered = message or ""
    for token, value in context.items():
        rendered = rendered.replace(token, str(value or "-"))
    return rendered


def provider_reference_from_response(result):
    if not isinstance(result, dict):
        return ""
    messages_data = result.get("messages") or []
    if not messages_data:
        return ""
    return messages_data[0].get("id", "")


def process_scheduled_whatsapp_messages(limit=50, now=None):
    now = now or timezone.now()
    due_logs = list(
        WhatsAppMessageLog.objects.select_related("integration", "template")
        .filter(
            status=WhatsAppMessageLog.Status.SCHEDULED,
            scheduled_for__isnull=False,
            scheduled_for__lte=now,
        )
        .order_by("scheduled_for", "created_at")[:limit]
    )
    summary = {"processed": 0, "sent": 0, "dry_run": 0, "failed": 0}

    for log in due_logs:
        integration = log.integration or WhatsAppIntegration.load()
        try:
            result = send_whatsapp_text(log.recipient_number, log.rendered_message, integration=integration)
        except IntegrationError as exc:
            log.status = WhatsAppMessageLog.Status.FAILED
            log.error_message = str(exc)
            log.response_payload = {}
            log.save(update_fields=["status", "error_message", "response_payload", "updated_at"])
            summary["failed"] += 1
            summary["processed"] += 1
            continue

        log.status = (
            WhatsAppMessageLog.Status.DRY_RUN
            if isinstance(result, dict) and result.get("dry_run")
            else WhatsAppMessageLog.Status.SENT
        )
        log.sent_at = timezone.now()
        log.error_message = ""
        log.provider_reference = provider_reference_from_response(result)
        log.response_payload = result if isinstance(result, dict) else {}
        log.save(
            update_fields=[
                "status",
                "sent_at",
                "error_message",
                "provider_reference",
                "response_payload",
                "updated_at",
            ]
        )
        key = "dry_run" if log.status == WhatsAppMessageLog.Status.DRY_RUN else "sent"
        summary[key] += 1
        summary["processed"] += 1

    return summary
