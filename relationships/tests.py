from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from core.models import (
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from patients.models import Patient


@override_settings(SECURE_SSL_REDIRECT=False)
class RelationshipsAccessAndExperienceTests(TestCase):
    def setUp(self):
        self.management = get_user_model().objects.create_user(
            username="gestao-relacionamento",
            password="Senha@123",
        )
        self.administration = get_user_model().objects.create_user(
            username="admin-relacionamento",
            password="Senha@123",
        )
        self.patient_user = get_user_model().objects.create_user(
            username="paciente-relacionamento",
            password="Senha@123",
        )
        self.professional_user = get_user_model().objects.create_user(
            username="profissional-relacionamento",
            password="Senha@123",
        )
        self.superuser = get_user_model().objects.create_superuser(
            username="suporte-relacionamento",
            password="Senha@123",
            email="suporte@example.com",
        )
        self.patient = Patient.objects.create(
            full_name="Paciente Relacionamento",
            phone="11999990000",
            birth_date=timezone.localdate(),
        )
        UserProfile.objects.update_or_create(
            user=self.management,
            defaults={"role": UserProfile.Role.MANAGEMENT},
        )
        UserProfile.objects.update_or_create(
            user=self.administration,
            defaults={"role": UserProfile.Role.ADMINISTRATION},
        )
        UserProfile.objects.update_or_create(
            user=self.patient_user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        UserProfile.objects.update_or_create(
            user=self.professional_user,
            defaults={"role": UserProfile.Role.PROFESSIONAL},
        )
        self.integration = WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "clinic_whatsapp_number": "5511999990000",
                "dry_run": True,
            },
        )[0]
        WhatsAppMessageTemplate.ensure_defaults()
        self.template = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT
        )

    def login(self, user):
        self.client.force_login(user)

    def test_management_sees_relationship_navigation_and_overview(self):
        self.login(self.management)

        response = self.client.get(reverse("relationships:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relacionamento")
        self.assertContains(response, "Hoje")
        self.assertContains(response, reverse("relationships:automations"))

    def test_administration_can_access_relationship_flow(self):
        self.login(self.administration)

        for route in [
            "relationships:overview",
            "relationships:automations",
            "relationships:history",
            "whatsapp_settings",
        ]:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_patient_and_professional_cannot_access_relationship_flow(self):
        for user in [self.patient_user, self.professional_user]:
            self.login(user)
            with self.subTest(role=user.username):
                response = self.client.get(reverse("relationships:overview"))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], reverse("dashboard"))

    def test_support_is_superuser_only(self):
        self.login(self.management)
        response = self.client.get(reverse("whatsapp_support"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("whatsapp_settings"))

        self.login(self.superuser)
        response = self.client.get(reverse("whatsapp_support"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Suporte técnico")

    def test_old_integration_routes_redirect_to_new_experience(self):
        cases = [
            ("", reverse("relationships:overview")),
            ("?tab=messages", reverse("relationships:automations")),
            ("?tab=panel", reverse("relationships:history")),
            ("?tab=connections", reverse("whatsapp_settings")),
            ("?tab=diagnostics", reverse("whatsapp_settings")),
        ]
        self.login(self.management)
        for suffix, destination in cases:
            with self.subTest(suffix=suffix):
                response = self.client.get(f"{reverse('integrations')}{suffix}")
                self.assertRedirects(response, destination, fetch_redirect_response=False)

        self.login(self.superuser)
        response = self.client.get(f"{reverse('integrations')}?tab=diagnostics")
        self.assertRedirects(
            response,
            reverse("whatsapp_support"),
            fetch_redirect_response=False,
        )

    @patch("core.web.whatsapp_settings.whatsapp_web_gateway_status")
    def test_normal_whatsapp_screen_uses_real_gateway_state(self, gateway_status):
        self.login(self.management)
        gateway_status.return_value = {
            "ok": True,
            "ready": False,
            "hasQr": False,
            "connectedNumber": "",
        }

        response = self.client.get(reverse("whatsapp_settings"))

        self.assertContains(response, "WhatsApp não conectado")
        self.assertNotContains(response, "WhatsApp conectado")

        gateway_status.return_value = {
            "ok": True,
            "ready": True,
            "hasQr": False,
            "connectedNumber": "5511988887777",
        }
        response = self.client.get(reverse("whatsapp_settings"))
        self.assertContains(response, "WhatsApp conectado")
        self.assertContains(response, "5511988887777")
        self.assertContains(response, "Desconectar WhatsApp")
        self.assertContains(response, "Trocar aparelho")

    @patch("core.web.whatsapp_settings.whatsapp_web_gateway_logout")
    def test_disconnect_logs_out_real_session_and_preserves_configuration(
        self,
        gateway_logout,
    ):
        self.login(self.management)
        original_number = self.integration.clinic_whatsapp_number
        self.integration.connected_at = timezone.now()
        self.integration.save(update_fields=["connected_at", "updated_at"])

        response = self.client.post(
            reverse("whatsapp_settings"),
            {"action": "disconnect"},
        )

        self.assertRedirects(
            response,
            reverse("whatsapp_settings"),
            fetch_redirect_response=False,
        )
        gateway_logout.assert_called_once_with()
        self.integration.refresh_from_db()
        self.assertIsNone(self.integration.connected_at)
        self.assertTrue(self.integration.enabled)
        self.assertEqual(
            self.integration.clinic_whatsapp_number,
            original_number,
        )

    @patch("core.web.whatsapp_settings.whatsapp_web_gateway_status")
    def test_normal_whatsapp_screen_hides_technical_concepts(self, gateway_status):
        self.login(self.management)
        gateway_status.return_value = {"ok": True, "ready": False, "hasQr": True}

        response = self.client.get(reverse("whatsapp_settings"))

        for hidden_text in ["Google", "Provider", "DDI", "Meta", "dry-run", "Processar fila"]:
            with self.subTest(hidden_text=hidden_text):
                self.assertNotContains(response, hidden_text)

    @patch("core.web.whatsapp_settings.whatsapp_web_gateway_status")
    def test_disconnected_screen_polls_the_qr_endpoint(self, gateway_status):
        self.login(self.management)
        gateway_status.return_value = {
            "ok": True,
            "state": "connecting",
            "ready": False,
            "hasQr": False,
            "connectedNumber": "",
        }

        response = self.client.get(reverse("whatsapp_settings"))

        self.assertContains(response, 'data-whatsapp-qr-poller')
        self.assertContains(
            response,
            f'data-qr-url="{reverse("integrations_whatsapp_web_qr")}"',
        )
        self.assertContains(
            response,
            f'data-status-url="{reverse("integrations_whatsapp_web_status")}"',
        )

    @patch("core.web.integrations.whatsapp_web_gateway_qr")
    def test_qr_endpoint_returns_generated_data_url(self, gateway_qr):
        self.login(self.management)
        gateway_qr.return_value = {
            "ok": True,
            "state": "qr_ready",
            "ready": False,
            "hasQr": True,
            "qrDataUrl": "data:image/png;base64,qr-local",
        }

        response = self.client.get(reverse("integrations_whatsapp_web_qr"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["qrDataUrl"],
            "data:image/png;base64,qr-local",
        )

    def test_automations_show_only_supported_routines(self):
        self.login(self.management)

        response = self.client.get(reverse("relationships:automations"))

        for label in [
            "Confirmação da sessão",
            "Sessão próxima",
            "Aniversário",
            "Mensalidade a vencer",
            "Mensalidade no vencimento",
            "Mensalidade vencida",
            "Cobrança avulsa vencida",
        ]:
            self.assertContains(response, label)
        self.assertNotContains(response, "Pacote perto da validade")
        self.assertNotContains(response, "Saldo baixo")
        self.assertNotContains(response, "Criar automação")

    def test_history_uses_friendly_expired_copy_and_hides_retry(self):
        WhatsAppMessageLog.objects.create(
            integration=self.integration,
            template=self.template,
            patient=self.patient,
            recipient_name=self.patient.full_name,
            recipient_number=self.patient.phone,
            rendered_message="Lembrete vencido",
            status=WhatsAppMessageLog.Status.EXPIRED,
            scheduled_for=timezone.now() - timedelta(hours=2),
            expires_at=timezone.now() - timedelta(hours=1),
            terminal_reason="appointment_started",
            error_message="HTTP 503 raw gateway detail",
        )
        self.login(self.management)

        response = self.client.get(reverse("relationships:history"))

        self.assertContains(response, "não enviada porque o horário da sessão passou")
        self.assertNotContains(response, "HTTP 503")
        self.assertNotContains(response, "Tentar novamente")

    def test_history_shows_retry_only_for_eligible_manual_failure(self):
        log = WhatsAppMessageLog.objects.create(
            integration=self.integration,
            template=self.template,
            patient=self.patient,
            recipient_name=self.patient.full_name,
            recipient_number=self.patient.phone,
            rendered_message="Mensagem manual",
            status=WhatsAppMessageLog.Status.FAILED,
            scheduled_for=timezone.now() - timedelta(minutes=1),
            message_purpose=WhatsAppMessageLog.MessagePurpose.MANUAL,
            retry_policy=WhatsAppMessageLog.RetryPolicy.NONE,
            error_message="Falha anterior",
        )
        self.login(self.management)

        response = self.client.get(reverse("relationships:history"))

        self.assertContains(
            response,
            reverse("relationships:history_retry", args=[log.pk]),
        )
        self.assertContains(response, "Tentar novamente")

    def test_overview_surfaces_actionable_queue_counts(self):
        WhatsAppMessageLog.objects.create(
            integration=self.integration,
            template=self.template,
            patient=self.patient,
            recipient_name=self.patient.full_name,
            recipient_number=self.patient.phone,
            rendered_message="Aguardando",
            status=WhatsAppMessageLog.Status.SCHEDULED,
            scheduled_for=timezone.now() + timedelta(minutes=10),
        )
        WhatsAppMessageLog.objects.create(
            integration=self.integration,
            template=self.template,
            patient=self.patient,
            recipient_name=self.patient.full_name,
            recipient_number=self.patient.phone,
            rendered_message="Expirada",
            status=WhatsAppMessageLog.Status.EXPIRED,
            scheduled_for=timezone.now() - timedelta(hours=2),
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.login(self.management)

        response = self.client.get(reverse("relationships:overview"))

        self.assertContains(response, "1 aguardando envio")
        self.assertContains(response, "1 prazo encerrado")
