from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.db.models import Q
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.utils import timezone

from core.integrations.credentials import first_configured_value
from core.integrations.http import IntegrationError, get_json, post_form, post_json
from core.integrations.whatsapp_gateway_provider import get_whatsapp_provider
from core.integrations.whatsapp_provider import WhatsAppProviderError
from core.models import WhatsAppIntegration, WhatsAppMessageLog, WhatsAppMessageTemplate
from core.services.whatsapp_delivery_policy import (
    RETRY_DELAYS_MINUTES,
    calculate_next_retry,
    evaluate_delivery,
)


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
    try:
        return _whatsapp_provider().status().as_gateway_payload()
    except (IntegrationError, WhatsAppProviderError) as exc:
        return {
            "ok": False,
            "state": "error",
            "ready": False,
            "hasQr": False,
            "error": str(exc),
            "lastError": str(exc),
        }


def _whatsapp_provider():
    try:
        return get_whatsapp_provider()
    except ImproperlyConfigured as exc:
        raise IntegrationError(
            "O transporte do WhatsApp está configurado de forma inválida."
        ) from exc


def whatsapp_web_gateway_qr():
    return _whatsapp_provider().qr().as_gateway_payload()


def whatsapp_web_gateway_restart():
    return _whatsapp_provider().restart().as_gateway_payload()


def whatsapp_web_gateway_logout():
    return _whatsapp_provider().logout()


def send_whatsapp_text(to_number, message, integration=None, *, request_id=None):
    integration = integration or WhatsAppIntegration.load()
    target = normalize_whatsapp_number(to_number, integration.default_country_code)
    if integration.provider != WhatsAppIntegration.Provider.WEB_GATEWAY:
        integration.provider = WhatsAppIntegration.Provider.WEB_GATEWAY
        integration.save(update_fields=["provider", "updated_at"])
    if not integration.enabled:
        raise WhatsAppProviderError(
            "Integracao WhatsApp esta desativada.",
            code="INTEGRATION_DISABLED",
            retryable=True,
        )
    if integration.dry_run or settings.WHATSAPP_DRY_RUN:
        integration.last_test_at = timezone.now()
        integration.last_error = ""
        integration.save(update_fields=["last_test_at", "last_error", "updated_at"])
        return {
            "dry_run": True,
            "to": target,
            "message": message,
            "requestId": request_id or str(uuid4()),
        }
    result = _whatsapp_provider().send_text(
        to=target,
        message=message,
        request_id=request_id or str(uuid4()),
    )
    integration.last_test_at = timezone.now()
    integration.last_error = ""
    integration.save(update_fields=["last_test_at", "last_error", "updated_at"])
    return {
        "ok": True,
        "provider": result.provider,
        "requestId": result.request_id,
        "messageId": result.message_id,
    }


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


DELIVERY_CLAIM_MINUTES = 10


def process_scheduled_whatsapp_messages(limit=50, now=None):
    now = now or timezone.now()
    due_logs = list(
        WhatsAppMessageLog.objects.select_related(
            "integration",
            "template",
            "patient",
            "appointment",
            "payment",
            "charge",
        )
        .filter(
            status=WhatsAppMessageLog.Status.SCHEDULED,
            scheduled_for__isnull=False,
            scheduled_for__lte=now,
        )
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now))
        .order_by("scheduled_for", "created_at")[:limit]
    )
    summary = {
        "processed": 0,
        "sent": 0,
        "dry_run": 0,
        "failed": 0,
        "retried": 0,
        "expired": 0,
        "uncertain": 0,
    }

    def sync_notification_delivery(log, *, status, error_message="", reference="", attempted=False):
        try:
            notification = log.delivery_notification
        except ObjectDoesNotExist:
            return
        if attempted:
            notification.attempts += 1
            notification.last_attempt_at = now
        notification.error_message = error_message
        update_fields = [
            "attempts",
            "last_attempt_at",
            "error_message",
            "status",
            "sent_at",
            "metadata",
            "updated_at",
        ]
        if reference:
            notification.provider_reference = reference
            update_fields.append("provider_reference")
        if status == WhatsAppMessageLog.Status.FAILED:
            notification.status = "failed"
        elif status == WhatsAppMessageLog.Status.EXPIRED:
            notification.status = "skipped"
        elif status == WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN:
            notification.status = "failed"
            notification.metadata = {
                **(notification.metadata or {}),
                "delivery_uncertain": True,
            }
        elif status in {WhatsAppMessageLog.Status.SENT, WhatsAppMessageLog.Status.DRY_RUN}:
            notification.status = "sent"
            notification.sent_at = now
        notification.save(update_fields=update_fields)

    for log in due_logs:
        claimed = (
            WhatsAppMessageLog.objects.filter(
                pk=log.pk,
                status=WhatsAppMessageLog.Status.SCHEDULED,
                scheduled_for__isnull=False,
                scheduled_for__lte=now,
            )
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now))
            .update(lease_until=now + timedelta(minutes=DELIVERY_CLAIM_MINUTES))
        )
        if not claimed:
            continue
        log.refresh_from_db()

        decision = evaluate_delivery(log, now=now)
        if not decision.allowed:
            log.status = decision.terminal_status
            log.next_attempt_at = None
            log.lease_until = None
            log.terminal_reason = decision.reason_code
            log.error_message = decision.user_message
            log.response_payload = {"terminal_reason": decision.reason_code}
            log.save(
                update_fields=[
                    "status",
                    "next_attempt_at",
                    "lease_until",
                    "terminal_reason",
                    "error_message",
                    "response_payload",
                    "updated_at",
                ]
            )
            sync_notification_delivery(log, status=log.status, error_message=decision.user_message)
            summary["expired" if log.status == WhatsAppMessageLog.Status.EXPIRED else "failed"] += 1
            summary["processed"] += 1
            continue

        integration = log.integration or WhatsAppIntegration.load()
        log.attempt_count += 1
        try:
            result = send_whatsapp_text(
                log.recipient_number,
                log.rendered_message,
                integration=integration,
                request_id=str(log.delivery_request_id),
            )
        except IntegrationError as exc:
            error_message = str(exc)
            retryable = isinstance(exc, WhatsAppProviderError) and exc.retryable
            delivery_uncertain = (
                isinstance(exc, WhatsAppProviderError)
                and exc.delivery_uncertain
            )
            error_code = (
                exc.code if isinstance(exc, WhatsAppProviderError) else "UNSTRUCTURED_ERROR"
            )
            if delivery_uncertain:
                log.status = WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN
                log.next_attempt_at = None
                log.lease_until = None
                log.error_message = error_message
                log.provider_reference = ""
                log.terminal_reason = "provider_result_unknown"
                log.response_payload = {
                    "delivery_uncertain": True,
                    "code": error_code,
                    "error": error_message,
                }
                log.save(
                    update_fields=[
                        "status",
                        "next_attempt_at",
                        "lease_until",
                        "attempt_count",
                        "error_message",
                        "provider_reference",
                        "terminal_reason",
                        "response_payload",
                        "updated_at",
                    ]
                )
                sync_notification_delivery(
                    log,
                    status=log.status,
                    error_message=(
                        "Nao foi possivel confirmar o resultado do envio. "
                        "A mensagem nao sera repetida automaticamente."
                    ),
                    attempted=True,
                )
                summary["uncertain"] += 1
                summary["processed"] += 1
                continue

            retry_at = calculate_next_retry(
                log,
                now=now,
                retryable=retryable,
                delivery_uncertain=delivery_uncertain,
            )
            if retry_at:
                log.status = WhatsAppMessageLog.Status.SCHEDULED
                log.next_attempt_at = retry_at
                log.lease_until = None
                delay_minutes = int((retry_at - now).total_seconds() // 60)
                log.error_message = (
                    f"{error_message} Nova tentativa automatica em "
                    f"{delay_minutes} minuto(s)."
                )
                log.terminal_reason = ""
                summary["retried"] += 1
            else:
                retryable_before_limit = (
                    retryable
                    and log.retry_policy != WhatsAppMessageLog.RetryPolicy.NONE
                    and log.attempt_count < log.max_attempts
                )
                delay_index = min(max(log.attempt_count - 1, 0), len(RETRY_DELAYS_MINUTES) - 1)
                candidate_retry = now + timedelta(minutes=RETRY_DELAYS_MINUTES[delay_index])
                expired_before_retry = bool(
                    retryable_before_limit
                    and log.expires_at
                    and candidate_retry >= log.expires_at
                )
                log.status = (
                    WhatsAppMessageLog.Status.EXPIRED
                    if expired_before_retry
                    else WhatsAppMessageLog.Status.FAILED
                )
                log.next_attempt_at = None
                log.lease_until = None
                log.error_message = error_message
                log.terminal_reason = (
                    "retry_after_expiry"
                    if expired_before_retry
                    else (
                        "attempts_exhausted"
                        if retryable
                        and log.attempt_count >= log.max_attempts
                        else "permanent_failure"
                    )
                )
            log.response_payload = {"code": error_code}
            log.save(
                update_fields=[
                    "status",
                    "next_attempt_at",
                    "lease_until",
                    "attempt_count",
                    "error_message",
                    "terminal_reason",
                    "response_payload",
                    "updated_at",
                ]
            )
            sync_notification_delivery(
                log,
                status=log.status,
                error_message=error_message,
                attempted=True,
            )
            if not retry_at:
                summary["expired" if log.status == WhatsAppMessageLog.Status.EXPIRED else "failed"] += 1
            summary["processed"] += 1
            continue

        log.status = (
            WhatsAppMessageLog.Status.DRY_RUN
            if isinstance(result, dict) and result.get("dry_run")
            else WhatsAppMessageLog.Status.SENT
        )
        log.sent_at = now
        log.next_attempt_at = None
        log.lease_until = None
        log.error_message = ""
        log.terminal_reason = ""
        log.provider_reference = provider_reference_from_response(result)
        log.response_payload = result if isinstance(result, dict) else {}
        log.save(
            update_fields=[
                "status",
                "sent_at",
                "next_attempt_at",
                "lease_until",
                "attempt_count",
                "error_message",
                "terminal_reason",
                "provider_reference",
                "response_payload",
                "updated_at",
            ]
        )
        sync_notification_delivery(
            log,
            status=log.status,
            reference=log.provider_reference,
            attempted=True,
        )
        key = "dry_run" if log.status == WhatsAppMessageLog.Status.DRY_RUN else "sent"
        summary[key] += 1
        summary["processed"] += 1

    return summary
