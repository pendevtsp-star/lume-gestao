from io import BytesIO
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError, URLError
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from core.integrations.whatsapp_provider import WhatsAppProviderError
from core.models import WhatsAppIntegration, WhatsAppMessageLog, WhatsAppMessageTemplate
from core.integrations.whatsapp import process_scheduled_whatsapp_messages
from patients.models import Patient


class WhatsAppProviderFactoryTests(SimpleTestCase):
    @override_settings(
        WHATSAPP_TRANSPORT="legacy",
        WHATSAPP_WEB_GATEWAY_URL="http://legacy:3020",
        WHATSAPP_WEB_GATEWAY_TOKEN="legacy-token",
    )
    def test_factory_selects_only_legacy_provider(self):
        from core.integrations.whatsapp_gateway_provider import get_whatsapp_provider

        provider = get_whatsapp_provider()

        self.assertEqual(provider.transport, "legacy")
        self.assertEqual(provider.base_url, "http://legacy:3020")

    @override_settings(
        WHATSAPP_TRANSPORT="baileys",
        WHATSAPP_BAILEYS_GATEWAY_URL="http://baileys:3030",
        WHATSAPP_BAILEYS_GATEWAY_TOKEN="baileys-token",
    )
    def test_factory_selects_only_baileys_provider(self):
        from core.integrations.whatsapp_gateway_provider import get_whatsapp_provider

        provider = get_whatsapp_provider()

        self.assertEqual(provider.transport, "baileys")
        self.assertEqual(provider.base_url, "http://baileys:3030")

    @override_settings(WHATSAPP_TRANSPORT="both")
    def test_factory_rejects_ambiguous_transport(self):
        from core.integrations.whatsapp_gateway_provider import get_whatsapp_provider

        with self.assertRaises(ImproperlyConfigured):
            get_whatsapp_provider()

    def test_structured_gateway_error_is_preserved(self):
        from core.integrations.whatsapp_gateway_provider import GatewayWhatsAppProvider

        provider = GatewayWhatsAppProvider(
            transport="baileys",
            base_url="http://baileys:3030",
            token="token",
        )
        provider._request = Mock(
            return_value={
                "ok": False,
                "code": "DELIVERY_RESULT_UNKNOWN",
                "retryable": False,
                "deliveryUncertain": True,
                "error": "Não foi possível confirmar o resultado do envio.",
            }
        )

        with self.assertRaises(WhatsAppProviderError) as raised:
            provider.send_text(
                to="5511999990000",
                message="Teste",
                request_id="16dfce54-69f3-46ec-bf33-f353486f9197",
            )

        self.assertEqual(raised.exception.code, "DELIVERY_RESULT_UNKNOWN")
        self.assertFalse(raised.exception.retryable)
        self.assertTrue(raised.exception.delivery_uncertain)

    @patch("core.integrations.whatsapp_gateway_provider.request.urlopen")
    def test_unstructured_http_error_during_send_is_never_treated_as_success(
        self,
        urlopen,
    ):
        from core.integrations.whatsapp_gateway_provider import GatewayWhatsAppProvider

        urlopen.side_effect = HTTPError(
            "http://baileys:3030/send",
            502,
            "Bad Gateway",
            {},
            BytesIO(b'{"detail":"upstream unavailable"}'),
        )
        provider = GatewayWhatsAppProvider(
            transport="baileys",
            base_url="http://baileys:3030",
            token="token",
        )

        with self.assertRaises(WhatsAppProviderError) as raised:
            provider.send_text(
                to="5511999990000",
                message="Teste",
                request_id="16dfce54-69f3-46ec-bf33-f353486f9197",
            )

        self.assertEqual(raised.exception.code, "TRANSPORT_HTTP_502")
        self.assertFalse(raised.exception.retryable)
        self.assertTrue(raised.exception.delivery_uncertain)

    @patch("core.integrations.whatsapp_gateway_provider.request.urlopen")
    def test_network_failure_during_send_is_delivery_uncertain(self, urlopen):
        from core.integrations.whatsapp_gateway_provider import GatewayWhatsAppProvider

        urlopen.side_effect = URLError("connection reset")
        provider = GatewayWhatsAppProvider(
            transport="legacy",
            base_url="http://legacy:3020",
            token="token",
        )

        with self.assertRaises(WhatsAppProviderError) as raised:
            provider.send_text(
                to="5511999990000",
                message="Teste",
                request_id="16dfce54-69f3-46ec-bf33-f353486f9197",
            )

        self.assertFalse(raised.exception.retryable)
        self.assertTrue(raised.exception.delivery_uncertain)

    @patch("core.integrations.whatsapp_gateway_provider.request.urlopen")
    def test_known_session_not_ready_response_remains_retryable(self, urlopen):
        from core.integrations.whatsapp_gateway_provider import GatewayWhatsAppProvider

        urlopen.side_effect = HTTPError(
            "http://legacy:3020/send",
            503,
            "Service Unavailable",
            {},
            BytesIO(
                b'{"ok":false,"ready":false,'
                b'"error":"Sessao WhatsApp Web ainda nao conectada."}'
            ),
        )
        provider = GatewayWhatsAppProvider(
            transport="legacy",
            base_url="http://legacy:3020",
            token="token",
        )

        with self.assertRaises(WhatsAppProviderError) as raised:
            provider.send_text(
                to="5511999990000",
                message="Teste",
                request_id="16dfce54-69f3-46ec-bf33-f353486f9197",
            )

        self.assertTrue(raised.exception.retryable)
        self.assertFalse(raised.exception.delivery_uncertain)

    @patch("core.integrations.whatsapp_gateway_provider.request.urlopen")
    def test_successful_non_object_response_is_rejected(self, urlopen):
        from core.integrations.whatsapp_gateway_provider import GatewayWhatsAppProvider

        response = MagicMock()
        response.read.return_value = b"[]"
        urlopen.return_value.__enter__.return_value = response
        provider = GatewayWhatsAppProvider(
            transport="legacy",
            base_url="http://legacy:3020",
            token="token",
        )

        with self.assertRaises(WhatsAppProviderError) as raised:
            provider.status()

        self.assertEqual(raised.exception.code, "INVALID_TRANSPORT_RESPONSE")

    @patch(
        "core.integrations.whatsapp_gateway_provider.GatewayWhatsAppProvider.logout"
    )
    @override_settings(
        WHATSAPP_TRANSPORT="baileys",
        WHATSAPP_BAILEYS_GATEWAY_URL="http://baileys:3030",
        WHATSAPP_BAILEYS_GATEWAY_TOKEN="baileys-token",
    )
    def test_logout_delegates_to_selected_provider(self, provider_logout):
        from core.integrations.whatsapp import whatsapp_web_gateway_logout

        whatsapp_web_gateway_logout()

        provider_logout.assert_called_once_with()


class WhatsAppQueueProviderContractTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.patient = Patient.objects.create(
            full_name="Paciente Provider",
            phone="11999990000",
        )
        self.integration = WhatsAppIntegration.objects.create(
            enabled=True,
            dry_run=False,
            clinic_whatsapp_number="5511999990000",
        )
        self.template = WhatsAppMessageTemplate.objects.create(
            template_type=WhatsAppMessageTemplate.TemplateType.CUSTOM,
            title="Manual",
            body="Olá, [Paciente]!",
        )

    def create_log(self):
        return WhatsAppMessageLog.objects.create(
            integration=self.integration,
            template=self.template,
            patient=self.patient,
            recipient_name=self.patient.full_name,
            recipient_number=self.patient.phone,
            rendered_message="Mensagem segura",
            status=WhatsAppMessageLog.Status.SCHEDULED,
            scheduled_for=self.now,
            retry_policy=WhatsAppMessageLog.RetryPolicy.BOUNDED,
            max_attempts=4,
        )

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_queue_reuses_delivery_request_id_for_provider(self, send_mock):
        send_mock.return_value = {
            "ok": True,
            "provider": "baileys",
            "messageId": "provider-message",
        }
        log = self.create_log()

        process_scheduled_whatsapp_messages(now=self.now)

        UUID(str(log.delivery_request_id))
        self.assertEqual(
            send_mock.call_args.kwargs["request_id"],
            str(log.delivery_request_id),
        )

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_structured_uncertain_error_never_retries(self, send_mock):
        send_mock.side_effect = WhatsAppProviderError(
            "Não foi possível confirmar o envio.",
            code="DELIVERY_RESULT_UNKNOWN",
            retryable=False,
            delivery_uncertain=True,
        )
        log = self.create_log()

        first = process_scheduled_whatsapp_messages(now=self.now)
        second = process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(first["uncertain"], 1)
        self.assertEqual(second["processed"], 0)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN)
