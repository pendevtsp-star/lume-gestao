from django.core import mail
from django.test import TestCase, override_settings

from core.emailing import MarketingConsentRequired, send_marketing_email, send_transactional_email
from patients.models import Patient


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_TRANSACTIONAL_FROM_EMAIL="Lume Gestao <nao-responda@clinicafisiolume.com.br>",
    EMAIL_MARKETING_FROM_EMAIL="Lume Studio <contato@clinicafisiolume.com.br>",
)
class EmailDeliveryPolicyTests(TestCase):
    def test_transactional_email_uses_transactional_sender_and_html(self):
        send_transactional_email(
            subject="Aviso operacional",
            text_body="Texto operacional",
            html_body="<p>Texto operacional</p>",
            recipients=["paciente@lume.local"],
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "Lume Gestao <nao-responda@clinicafisiolume.com.br>")
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")

    def test_marketing_email_requires_patient_consent(self):
        patient = Patient.objects.create(full_name="Paciente", email="paciente@lume.local")

        with self.assertRaises(MarketingConsentRequired):
            send_marketing_email(
                patient=patient,
                subject="Novidade",
                text_body="Novidade",
                html_body="<p>Novidade</p>",
            )

    def test_marketing_email_uses_marketing_sender_after_consent(self):
        patient = Patient.objects.create(
            full_name="Paciente Autorizado",
            email="autorizado@lume.local",
            email_marketing_opt_in=True,
        )

        send_marketing_email(
            patient=patient,
            subject="Novidade",
            text_body="Novidade",
            html_body="<p>Novidade</p>",
        )

        self.assertEqual(mail.outbox[0].from_email, "Lume Studio <contato@clinicafisiolume.com.br>")
