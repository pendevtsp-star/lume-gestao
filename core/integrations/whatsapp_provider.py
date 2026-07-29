from dataclasses import dataclass
from typing import Protocol

from core.integrations.http import IntegrationError


@dataclass(frozen=True)
class WhatsAppConnectionStatus:
    state: str
    ready: bool
    qr_data_url: str = ""
    connected_number: str = ""
    last_error_code: str = ""
    last_error_message: str = ""

    def as_gateway_payload(self):
        return {
            "ok": self.state != "error",
            "state": self.state,
            "ready": self.ready,
            "hasQr": bool(self.qr_data_url),
            "qrDataUrl": self.qr_data_url,
            "connectedNumber": self.connected_number,
            "lastErrorCode": self.last_error_code,
            "lastError": self.last_error_message,
            "error": self.last_error_message if self.state == "error" else "",
        }


@dataclass(frozen=True)
class WhatsAppSendResult:
    message_id: str
    request_id: str
    provider: str


class WhatsAppProviderError(IntegrationError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool = False,
        delivery_uncertain: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = bool(retryable)
        self.delivery_uncertain = bool(delivery_uncertain)


class WhatsAppProvider(Protocol):
    def status(self) -> WhatsAppConnectionStatus:
        raise NotImplementedError

    def qr(self) -> WhatsAppConnectionStatus:
        raise NotImplementedError

    def restart(self) -> WhatsAppConnectionStatus:
        raise NotImplementedError

    def logout(self) -> None:
        raise NotImplementedError

    def send_text(
        self,
        *,
        to: str,
        message: str,
        request_id: str,
    ) -> WhatsAppSendResult:
        raise NotImplementedError
