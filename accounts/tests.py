from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from unittest.mock import patch

from accounts.forms import UserAccountForm
from accounts.models import UserProfile
from patients.models import Patient
from team.models import Professional


class UserProfileTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_profile_is_created_for_new_user(self):
        user = get_user_model().objects.create_user(username="teste", password="Senha@123")

        self.assertTrue(UserProfile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.role, UserProfile.Role.ADMINISTRATION)

    def test_user_account_form_clears_incompatible_links_when_role_changes(self):
        user = get_user_model().objects.create_user(username="profissional", password="Senha@123", email="pro@lume.com")
        professional = Professional.objects.create(full_name="Dra. Perfil", specialty=Professional.Specialty.PILATES)
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )

        form = UserAccountForm(
            data={
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "is_active": "on",
                "role": UserProfile.Role.MANAGEMENT,
                "professional": professional.pk,
            },
            instance=user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.role, UserProfile.Role.MANAGEMENT)
        self.assertIsNone(user.profile.professional)

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

    def test_user_account_form_rejects_duplicate_email(self):
        get_user_model().objects.create_user(username="email-existente", email="duplicado@lume.local", password="Senha@123")

        form = UserAccountForm(
            data={
                "username": "",
                "first_name": "Novo",
                "last_name": "Duplicado",
                "email": "duplicado@lume.local",
                "is_active": "on",
                "role": UserProfile.Role.ADMINISTRATION,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Este e-mail ja esta cadastrado.", form.errors["email"])

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
    def test_management_user_creation_generates_and_sends_temporary_password(self):
        manager = get_user_model().objects.create_user(username="gestor", password="Senha@123")
        UserProfile.objects.update_or_create(user=manager, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(manager)

        response = self.client.post(
            reverse("accounts:create"),
            {
                "username": "novoacesso",
                "first_name": "Novo",
                "last_name": "Acesso",
                "email": "novo@lume.local",
                "is_active": "on",
                "role": UserProfile.Role.ADMINISTRATION,
                "password": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="novoacesso")
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.profile.must_change_password)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("novoacesso", mail.outbox[0].body)
        self.assertIn("Senha temporaria", mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_management_user_creation_generates_username_from_name_when_blank(self):
        manager = get_user_model().objects.create_user(username="gestor-login", password="Senha@123")
        UserProfile.objects.update_or_create(user=manager, defaults={"role": UserProfile.Role.MANAGEMENT})
        get_user_model().objects.create_user(username="mariasilva", password="Senha@123")
        self.client.force_login(manager)

        response = self.client.post(
            reverse("accounts:create"),
            {
                "username": "",
                "first_name": "Maria",
                "last_name": "Silva",
                "email": "maria.silva@lume.local",
                "is_active": "on",
                "role": UserProfile.Role.ADMINISTRATION,
                "password": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username="mariasilva2").exists())

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

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    @patch("accounts.onboarding.send_whatsapp_text")
    def test_password_recovery_can_send_temporary_password_by_whatsapp(self, whatsapp_mock):
        whatsapp_mock.return_value = {"messages": [{"id": "wa-1"}]}
        patient = Patient.objects.create(full_name="Paciente Sem Email", phone="11999990000")
        user = get_user_model().objects.create_user(username="paciente-whatsapp", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": patient, "phone": patient.phone},
        )

        response = self.client.post(reverse("password_reset"), {"identifier": "paciente-whatsapp"})

        self.assertEqual(response.status_code, 302)
        whatsapp_mock.assert_called_once()
        user.refresh_from_db()
        self.assertFalse(user.check_password("Senha@123"))
        self.assertTrue(user.profile.must_change_password)

    @patch("accounts.onboarding.send_whatsapp_text")
    def test_password_recovery_dry_run_does_not_change_password(self, whatsapp_mock):
        whatsapp_mock.return_value = {"dry_run": True}
        patient = Patient.objects.create(full_name="Paciente Teste", phone="11999990000")
        user = get_user_model().objects.create_user(username="paciente-dry", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": patient, "phone": patient.phone},
        )

        response = self.client.post(reverse("password_reset"), {"identifier": "paciente-dry"})

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Senha@123"))
        self.assertFalse(user.profile.must_change_password)

    @patch("accounts.onboarding.send_whatsapp_text")
    @patch("accounts.views.EmailMultiAlternatives")
    def test_password_recovery_falls_back_to_whatsapp_when_email_fails(self, email_message_mock, whatsapp_mock):
        email_message_mock.return_value.send.side_effect = RuntimeError("SMTP indisponivel")
        whatsapp_mock.return_value = {"messages": [{"id": "wa-2"}]}
        patient = Patient.objects.create(full_name="Paciente Fallback", phone="11999990000")
        user = get_user_model().objects.create_user(
            username="paciente-fallback",
            email="fallback@lume.local",
            password="Senha@123",
        )
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": patient, "phone": patient.phone},
        )

        response = self.client.post(reverse("password_reset"), {"identifier": "paciente-fallback"})

        self.assertEqual(response.status_code, 302)
        email_message_mock.assert_called_once()
        whatsapp_mock.assert_called_once()
        user.refresh_from_db()
        self.assertFalse(user.check_password("Senha@123"))
        self.assertTrue(user.profile.must_change_password)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_recovery_limits_repeated_attempts(self):
        get_user_model().objects.create_user(
            username="recuperar-limite",
            email="recuperar-limite@lume.local",
            password="Senha@123",
        )

        for _ in range(6):
            response = self.client.post(reverse("password_reset"), {"identifier": "recuperar-limite"})
            self.assertEqual(response.status_code, 302)

        self.assertEqual(len(mail.outbox), 5)

    def test_first_access_requires_password_change_and_records_lgpd_consent(self):
        user = get_user_model().objects.create_user(username="primeiro-acesso", password="TempSenha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"must_change_password": True})
        self.client.login(username="primeiro-acesso", password="TempSenha@123")

        blocked_response = self.client.get(reverse("dashboard"))
        self.assertRedirects(blocked_response, reverse("accounts:force_password_change"))

        response = self.client.post(
            reverse("accounts:force_password_change"),
            {
                "new_password1": "SenhaFinal@123",
                "new_password2": "SenhaFinal@123",
                "accept_terms": "on",
                "accept_privacy": "on",
                "accept_sensitive_data": "on",
            },
        )

        self.assertRedirects(response, reverse("dashboard"))
        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertTrue(user.check_password("SenhaFinal@123"))
        self.assertFalse(user.profile.must_change_password)
        self.assertIsNotNone(user.profile.terms_accepted_at)
        self.assertIsNotNone(user.profile.privacy_policy_accepted_at)
        self.assertIsNotNone(user.profile.sensitive_data_consent_at)
        self.assertEqual(str(user.pk), self.client.session.get("_auth_user_id"))

    def test_legal_pages_are_public(self):
        for url_name, expected_text in [
            ("terms_of_use", "Termos de Uso"),
            ("privacy_policy", "Politica de Privacidade"),
            ("sensitive_data_consent", "Consentimento para Dados Sensiveis"),
        ]:
            response = self.client.get(reverse(url_name))
            self.assertContains(response, expected_text, status_code=200)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_test_email_command_uses_configured_backend(self):
        call_command("send_test_email", "teste@lume.local")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["teste@lume.local"])
        self.assertIn("configuracao de envio", mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_check_email_setup_validates_current_backend(self):
        output = StringIO()

        call_command("check_email_setup", stdout=output)

        self.assertIn("Conexao validada", output.getvalue())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
    )
    def test_check_email_setup_reports_incomplete_smtp(self):
        with self.assertRaises(CommandError):
            call_command("check_email_setup")

    def test_send_test_whatsapp_command_runs_in_dry_mode(self):
        from core.models import WhatsAppIntegration

        WhatsAppIntegration.objects.update_or_create(pk=1, defaults={"enabled": True, "dry_run": True})

        call_command("send_test_whatsapp", "11999990000", "--message", "Teste")

        integration = WhatsAppIntegration.load()
        self.assertIsNotNone(integration.last_test_at)

    def test_must_change_password_redirects_until_new_password_is_defined(self):
        user = get_user_model().objects.create_user(username="primeiroacesso", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"must_change_password": True})
        self.client.force_login(user)

        dashboard_response = self.client.get(reverse("dashboard"), secure=True)
        self.assertEqual(dashboard_response.status_code, 302)
        self.assertEqual(dashboard_response["Location"], reverse("accounts:force_password_change"))

        short_response = self.client.post(
            reverse("accounts:force_password_change"),
            {"new_password1": "1234567", "new_password2": "1234567"},
            secure=True,
        )
        self.assertContains(short_response, "Use pelo menos 8 caracteres.", status_code=200)

        mismatch_response = self.client.post(
            reverse("accounts:force_password_change"),
            {
                "new_password1": "NovaSenha@123",
                "new_password2": "OutraSenha@123",
                "accept_terms": "on",
                "accept_privacy": "on",
                "accept_sensitive_data": "on",
            },
            secure=True,
        )
        self.assertContains(mismatch_response, "As senhas devem ser iguais.", status_code=200)

        response = self.client.post(
            reverse("accounts:force_password_change"),
            {
                "new_password1": "NovaSenha@123",
                "new_password2": "NovaSenha@123",
                "accept_terms": "on",
                "accept_privacy": "on",
                "accept_sensitive_data": "on",
            },
            secure=True,
        )

        self.assertRedirects(response, reverse("dashboard"))
        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertTrue(user.check_password("NovaSenha@123"))
        self.assertFalse(user.profile.must_change_password)
        self.assertEqual(str(user.pk), self.client.session.get("_auth_user_id"))

    def test_management_can_deactivate_user_access(self):
        manager = get_user_model().objects.create_user(username="gestor-excluir", password="Senha@123")
        UserProfile.objects.update_or_create(user=manager, defaults={"role": UserProfile.Role.MANAGEMENT})
        target = get_user_model().objects.create_user(username="usuario-inativar", password="Senha@123")
        self.client.force_login(manager)

        response = self.client.post(reverse("accounts:delete", args=[target.pk]), {"delete_action": "deactivate"})

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_management_can_delete_user_access_now(self):
        manager = get_user_model().objects.create_user(username="gestor-remover", password="Senha@123")
        UserProfile.objects.update_or_create(user=manager, defaults={"role": UserProfile.Role.MANAGEMENT})
        target = get_user_model().objects.create_user(username="usuario-remover", password="Senha@123")
        self.client.force_login(manager)

        response = self.client.post(reverse("accounts:delete", args=[target.pk]), {"delete_action": "delete_now"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=target.pk).exists())

    def test_create_patient_users_requires_delivery_option(self):
        Patient.objects.create(full_name="Paciente Sem Login")

        with self.assertRaises(CommandError):
            call_command("create_patient_users")

    def test_create_patient_users_can_show_temporary_password(self):
        patient = Patient.objects.create(full_name="Maria Existente")

        call_command("create_patient_users", "--show-passwords")

        patient.refresh_from_db()
        self.assertTrue(hasattr(patient, "user_profile"))
        self.assertEqual(patient.user_profile.role, UserProfile.Role.PATIENT)
        self.assertTrue(patient.user_profile.must_change_password)


class ReadOnlyViewerAccessTests(TestCase):
    def setUp(self):
        self.viewer = get_user_model().objects.create_user(username="adminvisual", password="Visualizacao@123")
        UserProfile.objects.update_or_create(user=self.viewer, defaults={"role": UserProfile.Role.VIEWER})
        self.patient = Patient.objects.create(full_name="Paciente Visualizacao")
        self.client.force_login(self.viewer)

    def test_viewer_can_open_main_read_only_pages(self):
        urls = [
            reverse("dashboard"),
            reverse("patients:list"),
            reverse("scheduling:appointments"),
            reverse("scheduling:availabilities"),
            reverse("billing:payments"),
            reverse("reports:dashboard"),
            reverse("fiscal:dashboard"),
            reverse("accounts:list"),
            reverse("integrations"),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, secure=True).status_code, 200)

    def test_viewer_cannot_create_patient_from_web(self):
        response = self.client.post(
            reverse("patients:create"),
            {
                "full_name": "Paciente Criado Indevidamente",
                "active": "on",
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Patient.objects.filter(full_name="Paciente Criado Indevidamente").exists())

    def test_viewer_cannot_post_to_critical_management_pages(self):
        urls = [
            reverse("billing:expense_create"),
            reverse("scheduling:agenda_settings"),
            reverse("accounts:create"),
            reverse("settings"),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {}, secure=True).status_code, 403)

    def test_viewer_can_read_api_but_cannot_write(self):
        get_response = self.client.get("/api/v1/patients/", secure=True)
        post_response = self.client.post(
            "/api/v1/patients/",
            {"full_name": "Paciente API Indevido", "active": True},
            content_type="application/json",
            secure=True,
        )

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(post_response.status_code, 403)
        self.assertFalse(Patient.objects.filter(full_name="Paciente API Indevido").exists())
