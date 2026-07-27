import json

from django.test import RequestFactory, SimpleTestCase, override_settings

from core.integrations.http import IntegrationError
from core.integrations.webhooks import parse_json_webhook


@override_settings(DEBUG=False)
class JsonWebhookSecurityTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def parse(self, request):
        return parse_json_webhook(
            request,
            configured_token="segredo-forte",
            received_token=request.headers.get("asaas-access-token", ""),
            provider_name="Asaas",
        )

    def test_accepts_bounded_json_with_valid_token(self):
        request = self.factory.post(
            "/webhook/",
            data=json.dumps({"event": "PAYMENT_RECEIVED"}),
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="segredo-forte",
        )

        payload, token_valid = self.parse(request)

        self.assertTrue(token_valid)
        self.assertEqual(payload["event"], "PAYMENT_RECEIVED")

    def test_rejects_non_json_content_type(self):
        request = self.factory.post(
            "/webhook/",
            data="event=PAYMENT_RECEIVED",
            content_type="application/x-www-form-urlencoded",
            HTTP_ASAAS_ACCESS_TOKEN="segredo-forte",
        )

        with self.assertRaisesMessage(IntegrationError, "Content-Type application/json"):
            self.parse(request)

    @override_settings(LUME_WEBHOOK_MAX_BODY_BYTES=16)
    def test_rejects_body_over_the_configured_limit(self):
        request = self.factory.post(
            "/webhook/",
            data=json.dumps({"event": "PAYMENT_RECEIVED"}),
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="segredo-forte",
        )

        with self.assertRaisesMessage(IntegrationError, "excede o limite"):
            self.parse(request)

    def test_rejects_invalid_token(self):
        request = self.factory.post(
            "/webhook/",
            data="{}",
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="errado",
        )

        with self.assertRaisesMessage(IntegrationError, "Token do webhook Asaas invalido"):
            self.parse(request)
