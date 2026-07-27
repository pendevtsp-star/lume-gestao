import hmac
import json

from django.conf import settings

from core.integrations.credentials import first_configured_value
from core.integrations.http import IntegrationError


def parse_json_webhook(request, *, configured_token, received_token, provider_name):
    """Validate a token and bounded JSON body before business processing."""
    expected = first_configured_value(configured_token)
    received = received_token or ""
    token_valid = bool(expected and received and hmac.compare_digest(received, expected))
    if not expected and not settings.DEBUG:
        raise IntegrationError(f"Configure o token do webhook {provider_name} antes de recebe-lo em producao.")
    if expected and not token_valid:
        raise IntegrationError(f"Token do webhook {provider_name} invalido.")

    content_type = (request.content_type or "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise IntegrationError("O webhook deve usar Content-Type application/json.")

    max_bytes = int(getattr(settings, "LUME_WEBHOOK_MAX_BODY_BYTES", 262_144))
    try:
        declared_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        declared_length = 0
    if declared_length > max_bytes:
        raise IntegrationError("Payload de webhook excede o limite permitido.")

    body = request.body
    if len(body) > max_bytes:
        raise IntegrationError("Payload de webhook excede o limite permitido.")
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError) as exc:
        raise IntegrationError(f"Payload de webhook {provider_name} invalido.") from exc
    if not isinstance(payload, dict):
        raise IntegrationError(f"Payload de webhook {provider_name} invalido.")
    return payload, token_valid
