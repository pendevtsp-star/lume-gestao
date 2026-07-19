from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.conf import settings
from django.utils import timezone

from core.integrations.credentials import first_configured_value
from core.integrations.http import IntegrationError, get_json, post_form, post_json
from core.models import WhatsAppIntegration, WhatsAppMessageLog, WhatsAppMessageTemplate


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
        first_configured_value(integration.embedded_app_id, settings.WHATSAPP_EMBEDDED_APP_ID),
        first_configured_value(integration.embedded_config_id, settings.WHATSAPP_EMBEDDED_CONFIG_ID),
        first_configured_value(integration.embedded_app_secret, settings.WHATSAPP_EMBEDDED_APP_SECRET),
    )


def whatsapp_embedded_signup_configured(integration=None):
    return all(whatsapp_embedded_signup_credentials(integration))


def whatsapp_runtime_state(integration=None, templates=None):
    integration = integration or WhatsAppIntegration.load()
    templates = list(templates if templates is not None else WhatsAppMessageTemplate.ensure_defaults())
    dry_run = bool(integration.dry_run or settings.WHATSAPP_DRY_RUN)
    active_templates = [template for template in templates if template.active]
    templates_ready = bool(active_templates)
    web_gateway_mode = True

    blockers = []
    if integration.provider != WhatsAppIntegration.Provider.WEB_GATEWAY:
        integration.provider = WhatsAppIntegration.Provider.WEB_GATEWAY
        integration.save(update_fields=["provider", "updated_at"])
    if not integration.enabled:
        blockers.append("not_connected")
    if not integration.clinic_whatsapp_number:
        blockers.append("clinic_number")
    if not settings.WHATSAPP_WEB_GATEWAY_URL:
        blockers.append("web_gateway_url")

    if integration.enabled and integration.clinic_whatsapp_number and settings.WHATSAPP_WEB_GATEWAY_URL:
        code = "web_gateway_ready"
        label = "WhatsApp Web ativo"
        detail = "O Lume envia mensagens automaticamente por uma sessao WhatsApp Web pareada por QR."
        next_step = "Mantenha a sessao pareada e acompanhe a fila de mensagens."
    else:
        code = "web_gateway_setup"
        label = "WhatsApp Web pendente"
        detail = "Informe o numero oficial da clinica e mantenha a integracao ativa para usar o gateway."
        next_step = "Informe o numero, salve a configuracao e escaneie o QR do WhatsApp Web."

    return {
        "code": code,
        "label": label,
        "detail": detail,
        "next_step": next_step,
        "dry_run": dry_run,
        "embedded_configured": False,
        "phone_number_id_configured": False,
        "access_token_configured": False,
        "templates_ready": templates_ready,
        "active_templates_total": len(active_templates),
        "web_gateway_mode": web_gateway_mode,
        "blockers": blockers,
    }


def whatsapp_connection_guidance(integration=None, templates=None):
    integration = integration or WhatsAppIntegration.load()
    state = whatsapp_runtime_state(integration, templates)
    raw_error = (integration.last_error or "").strip()
    normalized_error = raw_error.lower()

    tips = [
        "Mantenha a sessao do WhatsApp Web pareada no servidor para a fila automatica funcionar.",
        "Use o numero oficial da clinica salvo nesta tela.",
        "Se a sessao cair, escaneie o QR novamente antes de liberar novas automacoes.",
    ]

    error_title = ""
    error_detail = ""
    if raw_error:
        error_title = "O WhatsApp Web devolveu um erro."
        error_detail = "Confira se a sessao esta pareada e se o gateway esta em execucao antes de tentar novo envio."

    return {
        "state": state,
        "tips": tips,
        "error_title": error_title,
        "error_detail": error_detail,
        "show_debug_hint": bool(raw_error),
    }


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


def connect_whatsapp_embedded_signup(*, code="", browser_access_token="", integration=None):
    integration = integration or WhatsAppIntegration.load()
    if code:
        return exchange_whatsapp_embedded_signup_code(code, integration=integration)
    if not browser_access_token:
        raise IntegrationError("A Meta nao retornou o codigo de autorizacao nem um token de acesso.")
    integration.access_token = browser_access_token
    integration.enabled = True
    integration.connected_at = timezone.now()
    integration.last_error = ""
    integration.save(update_fields=["access_token", "enabled", "connected_at", "last_error", "updated_at"])
    return {"access_token": browser_access_token, "source": "browser_auth_response"}


def subscribe_whatsapp_business_account(integration=None):
    integration = integration or WhatsAppIntegration.load()
    access_token = first_configured_value(integration.access_token, settings.WHATSAPP_META_ACCESS_TOKEN)
    if not access_token:
        raise IntegrationError("Token ausente para inscrever o app nos webhooks da WABA.")
    if not integration.business_account_id:
        raise IntegrationError("WABA ID ausente para inscrever o app nos webhooks.")
    return post_json(
        f"https://graph.facebook.com/{settings.WHATSAPP_META_API_VERSION}/{integration.business_account_id}/subscribed_apps",
        {},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=settings.WHATSAPP_TIMEOUT,
    )


def whatsapp_web_gateway_headers():
    headers = {}
    if settings.WHATSAPP_WEB_GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {settings.WHATSAPP_WEB_GATEWAY_TOKEN}"
    return headers


def whatsapp_web_gateway_status():
    if not settings.WHATSAPP_WEB_GATEWAY_URL:
        return {
            "ok": False,
            "ready": False,
            "error": "WHATSAPP_WEB_GATEWAY_URL ausente.",
            "lastError": "",
        }
    try:
        status = get_json(
            f"{settings.WHATSAPP_WEB_GATEWAY_URL.rstrip('/')}/healthz",
            headers=whatsapp_web_gateway_headers(),
            timeout=min(settings.WHATSAPP_TIMEOUT, 5),
        )
        if not isinstance(status, dict):
            return {
                "ok": False,
                "ready": False,
                "error": "Resposta invalida do gateway WhatsApp Web.",
                "lastError": "",
            }
        status.setdefault("error", "")
        status.setdefault("lastError", "")
        status.setdefault("hasQr", bool(status.get("qr")))
        return status
    except IntegrationError as exc:
        return {"ok": False, "ready": False, "error": str(exc), "lastError": ""}


def whatsapp_web_gateway_qr():
    if not settings.WHATSAPP_WEB_GATEWAY_URL:
        raise IntegrationError("WHATSAPP_WEB_GATEWAY_URL ausente.")
    return get_json(
        f"{settings.WHATSAPP_WEB_GATEWAY_URL.rstrip('/')}/qr",
        headers=whatsapp_web_gateway_headers(),
        timeout=min(settings.WHATSAPP_TIMEOUT, 5),
    )


def send_whatsapp_text(to_number, message, integration=None):
    integration = integration or WhatsAppIntegration.load()
    target = normalize_whatsapp_number(to_number, integration.default_country_code)
    if integration.provider != WhatsAppIntegration.Provider.WEB_GATEWAY:
        integration.provider = WhatsAppIntegration.Provider.WEB_GATEWAY
        integration.save(update_fields=["provider", "updated_at"])
    if not integration.enabled:
        raise IntegrationError("Integracao WhatsApp esta desativada.")
    if integration.dry_run or settings.WHATSAPP_DRY_RUN:
        integration.last_test_at = timezone.now()
        integration.last_error = ""
        integration.save(update_fields=["last_test_at", "last_error", "updated_at"])
        return {"dry_run": True, "to": target, "message": message}
    if not settings.WHATSAPP_WEB_GATEWAY_URL:
        raise IntegrationError("O gateway do WhatsApp Web ainda nao esta configurado.")
    response = post_json(
        f"{settings.WHATSAPP_WEB_GATEWAY_URL.rstrip('/')}/send",
        {"to": target, "message": message},
        headers=whatsapp_web_gateway_headers(),
        timeout=settings.WHATSAPP_TIMEOUT,
    )
    integration.last_test_at = timezone.now()
    integration.last_error = ""
    integration.save(update_fields=["last_test_at", "last_error", "updated_at"])
    return response


def send_whatsapp_template(to_number, template, parameters, integration=None):
    integration = integration or WhatsAppIntegration.load()
    target = normalize_whatsapp_number(to_number, integration.default_country_code)
    if not integration.enabled:
        raise IntegrationError("Integracao WhatsApp esta desativada.")
    if integration.provider != WhatsAppIntegration.Provider.META:
        raise IntegrationError("Envio por template esta disponivel apenas para Meta Cloud API.")
    if integration.dry_run or settings.WHATSAPP_DRY_RUN:
        integration.last_test_at = timezone.now()
        integration.last_error = ""
        integration.save(update_fields=["last_test_at", "last_error", "updated_at"])
        return {
            "dry_run": True,
            "to": target,
            "template": template.meta_template_name,
            "language": template.meta_template_language,
            "parameters": parameters,
        }
    if not template.meta_template_name:
        raise IntegrationError("Template nao configurado para producao. Informe o nome aprovado na Meta.")
    access_token = first_configured_value(integration.access_token, settings.WHATSAPP_META_ACCESS_TOKEN)
    if not access_token:
        raise IntegrationError("Token ausente ou expirado. Reconecte o WhatsApp pela Meta.")
    phone_number_id = first_configured_value(integration.phone_number_id, settings.WHATSAPP_META_PHONE_NUMBER_ID)
    if not phone_number_id:
        raise IntegrationError("Phone Number ID ausente. Reconecte o WhatsApp pela Meta.")

    url = f"https://graph.facebook.com/{settings.WHATSAPP_META_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": target,
        "type": "template",
        "template": {
            "name": template.meta_template_name,
            "language": {"code": template.meta_template_language or "pt_BR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(value or "-")} for value in parameters],
                }
            ],
        },
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


def meta_template_parameters(template, context):
    return [context.get(token, "-") for token in template.variable_tokens]


def provider_reference_from_response(result):
    if not isinstance(result, dict):
        return ""
    if result.get("messageId"):
        return result["messageId"]
    messages_data = result.get("messages") or []
    if not messages_data:
        return ""
    return messages_data[0].get("id", "")


MAX_DELIVERY_ATTEMPTS = 4
RETRY_DELAYS_MINUTES = (2, 5, 15)


def transient_whatsapp_delivery_error(message):
    normalized = str(message or "").lower()
    transient_markers = (
        "http 502",
        "http 503",
        "http 504",
        "session not connected",
        "sessao whatsapp web",
        "sessao nao conectada",
        "gateway",
        "no lid for user",
    )
    return any(marker in normalized for marker in transient_markers)


def process_scheduled_whatsapp_messages(limit=50, now=None):
    now = now or timezone.now()
    due_logs = list(
        WhatsAppMessageLog.objects.select_related("integration", "template")
        .filter(
            status=WhatsAppMessageLog.Status.SCHEDULED,
            scheduled_for__isnull=False,
            scheduled_for__lte=now,
        )
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .order_by("scheduled_for", "created_at")[:limit]
    )
    summary = {"processed": 0, "sent": 0, "dry_run": 0, "failed": 0, "retried": 0}

    def sync_notification_delivery(log, *, status, error_message="", reference=""):
        try:
            notification = log.delivery_notification
        except Exception:
            return
        notification.attempts += 1
        notification.last_attempt_at = timezone.now()
        notification.error_message = error_message
        notification.provider_reference = reference
        if status == WhatsAppMessageLog.Status.FAILED:
            notification.status = "failed"
        elif status in {WhatsAppMessageLog.Status.SENT, WhatsAppMessageLog.Status.DRY_RUN}:
            notification.status = "sent"
            notification.sent_at = timezone.now()
        notification.save(
            update_fields=[
                "attempts",
                "last_attempt_at",
                "error_message",
                "provider_reference",
                "status",
                "sent_at",
                "updated_at",
            ]
        )

    for log in due_logs:
        integration = log.integration or WhatsAppIntegration.load()
        log.attempt_count += 1
        try:
            result = send_whatsapp_text(log.recipient_number, log.rendered_message, integration=integration)
        except IntegrationError as exc:
            error_message = str(exc)
            can_retry = transient_whatsapp_delivery_error(error_message) and log.attempt_count < MAX_DELIVERY_ATTEMPTS
            if can_retry:
                delay_index = min(log.attempt_count - 1, len(RETRY_DELAYS_MINUTES) - 1)
                log.status = WhatsAppMessageLog.Status.SCHEDULED
                log.next_attempt_at = now + timedelta(minutes=RETRY_DELAYS_MINUTES[delay_index])
                log.scheduled_for = log.next_attempt_at
                log.error_message = (
                    f"{error_message} Nova tentativa automatica em "
                    f"{RETRY_DELAYS_MINUTES[delay_index]} minuto(s)."
                )
                summary["retried"] += 1
            else:
                log.status = WhatsAppMessageLog.Status.FAILED
                log.next_attempt_at = None
                log.error_message = error_message
            log.response_payload = {}
            log.save(
                update_fields=[
                    "status",
                    "scheduled_for",
                    "next_attempt_at",
                    "attempt_count",
                    "error_message",
                    "response_payload",
                    "updated_at",
                ]
            )
            sync_notification_delivery(log, status=log.status, error_message=error_message)
            if not can_retry:
                summary["failed"] += 1
            summary["processed"] += 1
            continue

        log.status = (
            WhatsAppMessageLog.Status.DRY_RUN
            if isinstance(result, dict) and result.get("dry_run")
            else WhatsAppMessageLog.Status.SENT
        )
        log.sent_at = timezone.now()
        log.next_attempt_at = None
        log.error_message = ""
        log.provider_reference = provider_reference_from_response(result)
        log.response_payload = result if isinstance(result, dict) else {}
        log.save(
            update_fields=[
                "status",
                "sent_at",
                "next_attempt_at",
                "attempt_count",
                "error_message",
                "provider_reference",
                "response_payload",
                "updated_at",
            ]
        )
        sync_notification_delivery(log, status=log.status, reference=log.provider_reference)
        key = "dry_run" if log.status == WhatsAppMessageLog.Status.DRY_RUN else "sent"
        summary[key] += 1
        summary["processed"] += 1

    return summary
