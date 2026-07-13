from decimal import Decimal
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
    embedded_configured = whatsapp_embedded_signup_configured(integration)
    phone_number_id_configured = bool(
        first_configured_value(integration.phone_number_id, settings.WHATSAPP_META_PHONE_NUMBER_ID)
    )
    access_token_configured = bool(first_configured_value(integration.access_token, settings.WHATSAPP_META_ACCESS_TOKEN))
    active_templates = [template for template in templates if template.active]
    templates_ready = all(template.meta_template_name for template in active_templates)
    web_gateway_mode = integration.provider == WhatsAppIntegration.Provider.WEB_GATEWAY

    blockers = []
    if web_gateway_mode:
        if not integration.enabled:
            blockers.append("not_connected")
        if not integration.clinic_whatsapp_number:
            blockers.append("clinic_number")
        if not settings.WHATSAPP_WEB_GATEWAY_URL:
            blockers.append("web_gateway_url")
    elif not embedded_configured:
        blockers.append("embedded_signup")
    if not web_gateway_mode and not integration.enabled:
        blockers.append("not_connected")
    if not web_gateway_mode and not phone_number_id_configured:
        blockers.append("phone_number_id")
    if not web_gateway_mode and not dry_run and not access_token_configured:
        blockers.append("access_token")
    if not web_gateway_mode and not dry_run and not templates_ready:
        blockers.append("meta_templates")

    if web_gateway_mode and integration.enabled and integration.clinic_whatsapp_number and settings.WHATSAPP_WEB_GATEWAY_URL:
        code = "web_gateway_ready"
        label = "WhatsApp Web temporario ativo"
        detail = "O Lume envia mensagens automaticamente por uma sessao WhatsApp Web pareada por QR."
        next_step = "Abrir o QR do gateway, parear o celular uma vez e fazer um teste controlado."
    elif web_gateway_mode:
        code = "web_gateway_setup"
        label = "WhatsApp Web temporario pendente"
        detail = "Informe o numero oficial da clinica e mantenha a integracao ativa para usar o gateway."
        next_step = "Selecionar WhatsApp Web temporario, informar o numero da clinica e salvar a configuracao."
    elif not embedded_configured:
        code = "config_missing"
        label = "Configuracao tecnica pendente"
        detail = "Configure App ID, Configuration ID e App Secret para liberar a conexao pela Meta."
        next_step = "Preencher credenciais do Embedded Signup no .env ou na configuracao tecnica."
    elif not integration.enabled:
        code = "awaiting_meta"
        label = "Aguardando conexao Meta"
        detail = "A tela de conexao esta pronta, mas a Meta ainda nao devolveu os dados finais da conta oficial."
        next_step = "Abrir a Meta e concluir a conexao, priorizando o numero ja existente da clinica quando ele ja estiver em uso."
    elif not phone_number_id_configured:
        code = "missing_phone_number"
        label = "Numero nao vinculado"
        detail = "A conexao foi iniciada, mas a Meta ainda nao devolveu o identificador final do numero."
        next_step = "Reconectar pela Meta e, se o numero ja existir em outra conta, concluir pelo caminho de numero existente em vez de cadastrar um novo."
    elif dry_run:
        code = "connected_test"
        label = "Conectado em modo teste"
        detail = "O sistema pode simular envios sem disparar mensagens reais para pacientes."
        next_step = "Fazer teste controlado e manter WHATSAPP_DRY_RUN=True ate validar templates e numero."
    elif not access_token_configured:
        code = "missing_token"
        label = "Token Meta ausente"
        detail = "O envio real esta ligado, mas nao ha token disponivel para chamar a Cloud API."
        next_step = "Reconectar pela Meta ou configurar token valido antes de testar em producao."
    elif not templates_ready:
        code = "templates_pending"
        label = "Templates Meta pendentes"
        detail = "Ha modelos ativos sem nome de template aprovado na Meta."
        next_step = "Cadastrar os nomes aprovados na aba Mensagens antes de automacoes reais."
    else:
        code = "ready_live"
        label = "Pronto para envio real"
        detail = "Numero, token e templates ativos estao configurados."
        next_step = "Executar um teste real controlado antes de liberar automacoes."

    return {
        "code": code,
        "label": label,
        "detail": detail,
        "next_step": next_step,
        "dry_run": dry_run,
        "embedded_configured": embedded_configured,
        "phone_number_id_configured": phone_number_id_configured,
        "access_token_configured": access_token_configured,
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
        "Para entrega provisoria com disparo automatico, use WhatsApp Web temporario e mantenha a sessao pareada no servidor.",
        "Se a clinica ja usa esse WhatsApp no app Business, prefira conectar o numero existente em vez de cadastrar um novo.",
        "Use a mesma empresa/portfolio da Meta que ja e dona do numero para evitar bloqueios de propriedade.",
        "Depois que a Meta concluir a autorizacao, volte para esta tela e faca um teste controlado antes de liberar automacoes.",
    ]

    error_title = ""
    error_detail = ""
    if "133010" in normalized_error or "account not registered" in normalized_error:
        error_title = "A Meta ainda nao liberou esse numero para envio real."
        error_detail = (
            "Isso costuma acontecer quando o numero foi conectado, mas ainda nao ficou registrado na conta certa da Cloud API, "
            "ou quando o fluxo foi concluido como novo numero em vez de numero ja existente."
        )
    elif "ja esta registrado" in normalized_error or "já está registrado" in normalized_error:
        error_title = "Esse numero ja existe em outra conta da Meta."
        error_detail = (
            "Para seguir sem conflito, conclua a conexao usando o portfolio que ja possui o numero ou escolha o caminho de numero existente/migracao."
        )
    elif raw_error:
        error_title = "A Meta devolveu um erro na etapa final da conexao."
        error_detail = "Abra o diagnostico tecnico apenas se precisar conferir os detalhes para suporte."

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
        return {"ok": False, "ready": False, "error": "WHATSAPP_WEB_GATEWAY_URL ausente."}
    try:
        return get_json(
            f"{settings.WHATSAPP_WEB_GATEWAY_URL.rstrip('/')}/healthz",
            headers=whatsapp_web_gateway_headers(),
            timeout=min(settings.WHATSAPP_TIMEOUT, 5),
        )
    except IntegrationError as exc:
        return {"ok": False, "ready": False, "error": str(exc)}


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
        try:
            if integration.provider == WhatsAppIntegration.Provider.WEB_GATEWAY:
                result = send_whatsapp_text(log.recipient_number, log.rendered_message, integration=integration)
            elif integration.dry_run or settings.WHATSAPP_DRY_RUN or not log.template:
                result = send_whatsapp_text(log.recipient_number, log.rendered_message, integration=integration)
            else:
                from core.services.whatsapp_automation import build_whatsapp_message_context

                context = build_whatsapp_message_context(
                    patient=log.patient,
                    appointment=log.appointment,
                    payment=log.payment,
                    charge=log.charge,
                )
                result = send_whatsapp_template(
                    log.recipient_number,
                    log.template,
                    meta_template_parameters(log.template, context),
                    integration=integration,
                )
        except IntegrationError as exc:
            log.status = WhatsAppMessageLog.Status.FAILED
            log.error_message = str(exc)
            log.response_payload = {}
            log.save(update_fields=["status", "error_message", "response_payload", "updated_at"])
            sync_notification_delivery(log, status=log.status, error_message=str(exc))
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
        sync_notification_delivery(log, status=log.status, reference=log.provider_reference)
        key = "dry_run" if log.status == WhatsAppMessageLog.Status.DRY_RUN else "sent"
        summary[key] += 1
        summary["processed"] += 1

    return summary
