from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.forms import (
    CustomWhatsAppMessageTemplateForm,
    WhatsAppAutomationRuleForm,
    WhatsAppMessageTemplateForm,
)
from core.models import (
    WhatsAppAutomationRule,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from core.services.whatsapp_configuration import (
    automation_rule_operational_states,
    template_variable_documentation,
    whatsapp_web_connection_state,
)
from core.views import IntegrationsView
from patients.models import Patient
from scheduling.models import Appointment
from team.models import Professional


class WhatsAppTemplateValidationTests(TestCase):
    def setUp(self):
        self.template = WhatsAppMessageTemplate.objects.create(
            template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT,
            title="Lembrete",
            description="Aviso da agenda",
            body="Ola, [Paciente]! Sua sessao sera em [Data] as [Horario].",
        )

    def form_data(self, body):
        return {
            "active": "on",
            "title": "Lembrete",
            "description": "Aviso da agenda",
            "body": body,
            "send_time": "",
        }

    def test_template_form_rejects_unknown_variable(self):
        form = WhatsAppMessageTemplateForm(
            self.form_data("Ola, [Paciente]! Acesse [LinkPagamento]."),
            instance=self.template,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("[LinkPagamento]", form.errors["body"][0])

    def test_template_form_rejects_unclosed_variable(self):
        form = WhatsAppMessageTemplateForm(
            self.form_data("Ola, [Paciente! Sua sessao sera em [Data]."),
            instance=self.template,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("colchetes", form.errors["body"][0].lower())

    def test_template_form_accepts_documented_variables(self):
        form = WhatsAppMessageTemplateForm(
            self.form_data("Ola, [Paciente]! Sua sessao com [Profissional] sera em [Data] as [Horario]."),
            instance=self.template,
        )

        self.assertTrue(form.is_valid(), form.errors)
        documentation = template_variable_documentation(self.template.template_type)
        self.assertEqual(documentation[0]["token"], "[Paciente]")
        self.assertTrue(all(item["description"] and item["example"] for item in documentation))

    def test_custom_template_uses_documented_custom_variables(self):
        form = CustomWhatsAppMessageTemplateForm(
            {
                "active": "on",
                "title": "Confirmacao",
                "description": "Modelo da clinica",
                "body": "Ola, [Paciente]! Fale com [Clinica] em [TelefoneClinica].",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)


class WhatsAppAutomationRuleFormTests(TestCase):
    def test_appointment_rule_rejects_financial_template(self):
        template = WhatsAppMessageTemplate.objects.create(
            template_type=WhatsAppMessageTemplate.TemplateType.CHARGE,
            title="Cobranca",
            body="Ola, [Paciente]! O valor e [Valor].",
        )
        form = WhatsAppAutomationRuleForm(
            {
                "name": "Cobranca antes da sessao",
                "template": template.pk,
                "trigger": WhatsAppAutomationRule.Trigger.APPOINTMENT_BEFORE,
                "hours_before": 2,
                "active": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("agenda", form.errors["template"][0].lower())


class WhatsAppWebConnectionStateTests(TestCase):
    def test_connection_states_cover_the_complete_qr_journey(self):
        self.assertEqual(whatsapp_web_connection_state({}, enabled=False)["code"], "disconnected")
        self.assertEqual(whatsapp_web_connection_state({"ok": True}, enabled=True)["code"], "preparing")
        qr_state = whatsapp_web_connection_state(
            {"ok": True, "hasQr": True, "qrDataUrl": "data:image/png;base64,abc"},
            enabled=True,
        )
        self.assertEqual(qr_state["code"], "qr_ready")
        self.assertTrue(qr_state["show_qr"])
        self.assertEqual(
            whatsapp_web_connection_state({"ok": True, "ready": True}, enabled=True)["code"],
            "connected",
        )
        error_state = whatsapp_web_connection_state(
            {"ok": False, "error": "Gateway indisponivel"},
            enabled=True,
        )
        self.assertEqual(error_state["code"], "error")
        self.assertTrue(error_state["recoverable"])


class WhatsAppAutomationOperationalStateTests(TestCase):
    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)
        self.template = WhatsAppMessageTemplate.objects.create(
            template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT,
            title="Lembrete",
            body="Ola, [Paciente]! Sua sessao sera em [Data] as [Horario].",
        )
        self.rule = WhatsAppAutomationRule.objects.create(
            name="Lembrete 2 horas antes",
            template=self.template,
            trigger=WhatsAppAutomationRule.Trigger.APPOINTMENT_BEFORE,
            hours_before=2,
            active=True,
        )
        patient = Patient.objects.create(full_name="Maria", phone="82999990000")
        professional = Professional.objects.create(
            full_name="Thais",
            specialty=Professional.Specialty.PILATES,
        )
        self.appointment = Appointment.objects.create(
            patient=patient,
            professional=professional,
            starts_at=self.now + timedelta(hours=5),
            ends_at=self.now + timedelta(hours=6),
            status=Appointment.Status.SCHEDULED,
        )

    def test_rule_state_exposes_next_execution_last_send_and_retry(self):
        integration = WhatsAppIntegration.load()
        sent_log = WhatsAppMessageLog.objects.create(
            integration=integration,
            template=self.template,
            recipient_name="Maria",
            recipient_number="5582999990000",
            rendered_message="Mensagem",
            status=WhatsAppMessageLog.Status.SENT,
            sent_at=self.now - timedelta(hours=1),
        )
        retry_at = self.now + timedelta(minutes=15)
        WhatsAppMessageLog.objects.create(
            integration=integration,
            template=self.template,
            recipient_name="Maria",
            recipient_number="5582999990000",
            rendered_message="Mensagem",
            status=WhatsAppMessageLog.Status.FAILED,
            next_attempt_at=retry_at,
            error_message="Gateway temporariamente indisponivel",
        )

        state = automation_rule_operational_states([self.rule], now=self.now)[0]

        self.assertEqual(state["code"], "retrying")
        self.assertEqual(state["next_execution_at"], self.appointment.starts_at - timedelta(hours=2))
        self.assertEqual(state["last_sent_at"], sent_log.sent_at)
        self.assertEqual(state["next_retry_at"], retry_at)
        self.assertEqual(state["failure_count"], 1)

    def test_paused_rule_has_explicit_state(self):
        self.rule.active = False
        self.rule.save(update_fields=["active", "updated_at"])

        state = automation_rule_operational_states([self.rule], now=self.now)[0]

        self.assertEqual(state["code"], "paused")
        self.assertEqual(state["label"], "Pausada")


class WhatsAppOperationalContextTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/integracoes/?tab=connections")
        self.request.user = get_user_model().objects.create_user(
            username="integration-manager",
            password="not-used",
        )

    def build_context(self, gateway_status):
        view = IntegrationsView()
        view.setup(self.request)
        with patch("core.views.whatsapp_web_gateway_status", return_value=gateway_status):
            return view.build_context()

    def test_context_uses_single_whatsapp_web_connection_state(self):
        integration = WhatsAppIntegration.load()
        integration.enabled = True
        integration.save(update_fields=["enabled", "updated_at"])

        context = self.build_context(
            {"ok": True, "ready": False, "hasQr": True, "qrDataUrl": "data:image/png;base64,abc"}
        )

        self.assertEqual(context["whatsapp_connection_state"]["code"], "qr_ready")
        self.assertTrue(context["whatsapp_connection_state"]["show_qr"])
        self.assertEqual(context["whatsapp_channel_name"], "WhatsApp Web")
        self.assertFalse(context["google_operational"])

    def test_context_exposes_operational_state_for_each_automation_rule(self):
        template = WhatsAppMessageTemplate.objects.create(
            template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT,
            title="Lembrete",
            body="Ola, [Paciente]! Sua sessao sera em [Data] as [Horario].",
        )
        rule = WhatsAppAutomationRule.objects.create(
            name="Lembrete de sessao",
            template=template,
            trigger=WhatsAppAutomationRule.Trigger.APPOINTMENT_BEFORE,
            hours_before=24,
            active=False,
        )

        context = self.build_context({"ok": True, "ready": True})

        states = context["automation_rule_states"]
        state = next(item for item in states if item["rule"].pk == rule.pk)
        self.assertEqual(state["code"], "paused")
        self.assertIn("next_execution_at", state)
        self.assertIn("last_sent_at", state)
        self.assertIn("next_retry_at", state)


class WhatsAppOperationalTemplateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="whatsapp-operator",
            password="not-used",
            email="operator@example.com",
        )
        self.client.force_login(self.user)
        self.integration = WhatsAppIntegration.load()
        self.integration.enabled = True
        self.integration.save(update_fields=["enabled", "updated_at"])
        self.template = WhatsAppMessageTemplate.objects.create(
            template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT,
            title="Lembrete operacional",
            body="Ola, [Paciente]! Sua sessao sera em [Data] as [Horario].",
        )
        self.rule = WhatsAppAutomationRule.objects.create(
            name="Lembrete operacional - 24 horas",
            template=self.template,
            trigger=WhatsAppAutomationRule.Trigger.APPOINTMENT_BEFORE,
            hours_before=24,
            active=False,
        )

    @patch("core.views.whatsapp_web_gateway_status")
    def test_connection_page_renders_the_normalized_gateway_state(self, gateway_status):
        gateway_status.return_value = {"ok": True, "ready": True}

        response = self.client.get(reverse("integrations"), {"tab": "connections"})

        self.assertContains(response, "A sessao esta pronta para os envios e automacoes da clinica.")
        self.assertContains(response, "Canal unico de envio")

    @patch("core.views.whatsapp_web_gateway_status", return_value={"ok": True, "ready": True})
    def test_messages_page_renders_rule_telemetry_and_variable_documentation(self, _gateway_status):
        response = self.client.get(
            reverse("integrations"),
            {"tab": "messages", "message": "appointment"},
        )

        self.assertContains(response, "Proxima execucao")
        self.assertContains(response, "Ultimo envio")
        self.assertContains(response, "Variaveis deste modelo")
        self.assertContains(response, "[Paciente]")
