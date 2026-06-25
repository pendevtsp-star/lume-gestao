from django.conf import settings
from django.utils import timezone

from core.integrations.http import IntegrationError, post_json
from core.models import WhatsAppIntegration


def normalize_whatsapp_number(number, default_country_code="55"):
    digits = "".join(character for character in str(number or "") if character.isdigit())
    if not digits:
        raise IntegrationError("Informe um numero de WhatsApp.")
    if len(digits) <= 11 and default_country_code:
        digits = f"{default_country_code}{digits}"
    return digits


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
    if not settings.WHATSAPP_META_ACCESS_TOKEN:
        raise IntegrationError("Configure WHATSAPP_META_ACCESS_TOKEN no .env.")
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
        headers={"Authorization": f"Bearer {settings.WHATSAPP_META_ACCESS_TOKEN}"},
        timeout=settings.WHATSAPP_TIMEOUT,
    )
    integration.last_test_at = timezone.now()
    integration.last_error = ""
    integration.save(update_fields=["last_test_at", "last_error", "updated_at"])
    return response
