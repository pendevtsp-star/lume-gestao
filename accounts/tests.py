from django.contrib.auth import get_user_model
from django.test import TestCase
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
