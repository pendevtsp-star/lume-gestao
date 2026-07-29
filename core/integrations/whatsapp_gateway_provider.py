import json
from urllib import error, parse, request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from core.integrations.whatsapp_provider import (
    WhatsAppConnectionStatus,
    WhatsAppProviderError,
    WhatsAppSendResult,
)


ALLOWED_STATES = {
    "disabled",
    "disconnected",
    "qr_ready",
    "connecting",
    "ready",
    "reconnecting",
    "logged_out",
    "error",
}


class GatewayWhatsAppProvider:
    def __init__(self, *, transport, base_url, token):
        self.transport = transport
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        if not self.base_url:
            raise ImproperlyConfigured(
                f"URL do transportador WhatsApp {transport} não configurada."
            )

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method, path, payload=None):
        target = f"{self.base_url}{path}"
        parsed = parse.urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise WhatsAppProviderError(
                "Endereço do transportador WhatsApp inválido.",
                code="INVALID_TRANSPORT_URL",
            )
        body = (
            json.dumps(payload).encode("utf-8")
            if payload is not None
            else None
        )
        req = request.Request(
            target,
            data=body,
            headers=self._headers(),
            method=method,
        )
        try:
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with request.urlopen(req, timeout=settings.WHATSAPP_TIMEOUT) as response:  # nosec B310
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw_body = exc.read().decode("utf-8", errors="replace")
            try:
                response_payload = json.loads(raw_body)
            except json.JSONDecodeError:
                response_payload = {}
            if not isinstance(response_payload, dict):
                response_payload = {}
            sending = path == "/send"
            response_payload.setdefault("ok", False)
            response_payload.setdefault("code", f"TRANSPORT_HTTP_{exc.code}")
            response_payload.setdefault(
                "retryable",
                exc.code in {503, 504} and not sending,
            )
            response_payload.setdefault("deliveryUncertain", sending)
            response_payload.setdefault(
                "error",
                "O transportador WhatsApp não concluiu a solicitação.",
            )
            return response_payload
        except (error.URLError, TimeoutError) as exc:
            sending = path == "/send"
            raise WhatsAppProviderError(
                "O transportador WhatsApp está indisponível.",
                code="TRANSPORT_UNAVAILABLE",
                retryable=not sending,
                delivery_uncertain=sending,
            ) from exc

        if not raw_body:
            return {}
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise WhatsAppProviderError(
                "O transportador WhatsApp devolveu uma resposta inválida.",
                code="INVALID_TRANSPORT_RESPONSE",
                delivery_uncertain=path == "/send",
            ) from exc

    def _raise_for_error(self, payload):
        if payload.get("ok") is not False:
            return
        raise WhatsAppProviderError(
            payload.get("error") or "Falha no transportador WhatsApp.",
            code=payload.get("code") or "TRANSPORT_ERROR",
            retryable=payload.get("retryable", False),
            delivery_uncertain=payload.get("deliveryUncertain", False),
        )

    def _connection_status(self, payload):
        self._raise_for_error(payload)
        ready = bool(payload.get("ready"))
        qr_data_url = payload.get("qrDataUrl") or ""
        state = payload.get("state") or (
            "ready"
            if ready
            else "qr_ready"
            if qr_data_url or payload.get("hasQr")
            else "disconnected"
        )
        if state not in ALLOWED_STATES:
            state = "error"
        return WhatsAppConnectionStatus(
            state=state,
            ready=ready,
            qr_data_url=qr_data_url,
            connected_number=payload.get("connectedNumber") or "",
            last_error_code=payload.get("lastErrorCode") or "",
            last_error_message=payload.get("lastError") or "",
        )

    def status(self):
        return self._connection_status(self._request("GET", "/healthz"))

    def qr(self):
        return self._connection_status(self._request("GET", "/qr"))

    def restart(self):
        return self._connection_status(self._request("POST", "/restart", {}))

    def logout(self):
        payload = self._request("POST", "/logout", {})
        self._raise_for_error(payload)

    def send_text(self, *, to, message, request_id):
        payload = self._request(
            "POST",
            "/send",
            {
                "requestId": request_id,
                "to": to,
                "message": message,
            },
        )
        self._raise_for_error(payload)
        return WhatsAppSendResult(
            message_id=payload.get("messageId") or "",
            request_id=payload.get("requestId") or request_id,
            provider=payload.get("provider") or self.transport,
        )


def get_whatsapp_provider():
    transport = settings.WHATSAPP_TRANSPORT
    if transport == "legacy":
        return GatewayWhatsAppProvider(
            transport="legacy",
            base_url=settings.WHATSAPP_WEB_GATEWAY_URL,
            token=settings.WHATSAPP_WEB_GATEWAY_TOKEN,
        )
    if transport == "baileys":
        return GatewayWhatsAppProvider(
            transport="baileys",
            base_url=settings.WHATSAPP_BAILEYS_GATEWAY_URL,
            token=settings.WHATSAPP_BAILEYS_GATEWAY_TOKEN,
        )
    raise ImproperlyConfigured(
        "WHATSAPP_TRANSPORT deve ser exatamente 'legacy' ou 'baileys'."
    )
