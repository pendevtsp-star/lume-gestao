from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from accounts.models import UserProfile
from patients.models import Patient


class UserProfileTests(TestCase):
    def test_profile_is_created_for_new_user(self):
        user = get_user_model().objects.create_user(username="teste", password="Senha@123")

        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.role, UserProfile.Role.ADMINISTRATION)

    def test_user_can_update_own_login_and_password(self):
        user = get_user_model().objects.create_user(username="login-antigo", password="Senha@123")
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:self_settings"),
            {
                "username": "login-novo",
                "first_name": "Nome",
                "last_name": "Teste",
                "email": "novo@lume.local",
                "phone": "11999990000",
                "current_password": "Senha@123",
                "new_password1": "NovaSenha@123",
                "new_password2": "NovaSenha@123",
            },
        )

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.username, "login-novo")
        self.assertTrue(user.check_password("NovaSenha@123"))

    def test_user_cannot_reuse_existing_login(self):
        get_user_model().objects.create_user(username="login-existente", password="Senha@123")
        user = get_user_model().objects.create_user(username="login-proprio", password="Senha@123")
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:self_settings"),
            {
                "username": "login-existente",
                "first_name": "",
                "last_name": "",
                "email": "",
                "phone": "",
            },
        )

        self.assertContains(response, "Este login ja esta em uso.", status_code=200)

    def test_user_can_remove_current_profile_photo(self):
        patient = Patient.objects.create(full_name="Paciente Foto", photo="patients/photos/teste.jpg")
        user = get_user_model().objects.create_user(username="paciente-foto", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": patient})
        self.client.force_login(user)

        get_response = self.client.get(reverse("accounts:self_settings"))

        self.assertContains(get_response, "Remover foto")
        self.assertContains(get_response, "voce tem certeza que deseja excluir sua foto do perfil")

        response = self.client.post(
            reverse("accounts:self_settings"),
            {
                "username": "paciente-foto",
                "first_name": "",
                "last_name": "",
                "email": "",
                "phone": "",
                "remove_photo": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        patient.refresh_from_db()
        self.assertFalse(patient.photo)

    def test_management_user_can_save_whatsapp_settings(self):
        user = get_user_model().objects.create_user(username="gestor-whatsapp", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(user)

        response = self.client.post(
            reverse("accounts:self_settings"),
            {
                "username": "gestor-whatsapp",
                "first_name": "",
                "last_name": "",
                "email": "gestor@lume.local",
                "phone": "",
                "whatsapp_number": "5511999990000",
                "whatsapp_notifications_enabled": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.whatsapp_number, "5511999990000")
        self.assertTrue(user.profile.whatsapp_notifications_enabled)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_recovery_sends_email_for_existing_user(self):
        get_user_model().objects.create_user(
            username="recuperar",
            email="recuperar@lume.local",
            password="Senha@123",
        )

        response = self.client.post(reverse("password_reset"), {"identifier": "recuperar"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("recuperar-senha", mail.outbox[0].body)

    def test_password_recovery_reports_missing_user(self):
        response = self.client.post(reverse("password_reset"), {"identifier": "nao-existe"})

        self.assertContains(response, "Usuario inexistente.", status_code=200)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_test_email_command_uses_configured_backend(self):
        call_command("send_test_email", "teste@lume.local")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["teste@lume.local"])
        self.assertIn("configuracao de envio", mail.outbox[0].body)

    def test_send_test_whatsapp_command_runs_in_dry_mode(self):
        from core.models import WhatsAppIntegration

        WhatsAppIntegration.objects.update_or_create(pk=1, defaults={"enabled": True, "dry_run": True})

        call_command("send_test_whatsapp", "11999990000", "--message", "Teste")

        integration = WhatsAppIntegration.load()
        self.assertIsNotNone(integration.last_test_at)
