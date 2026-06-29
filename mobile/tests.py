from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import UserProfile
from billing.models import Membership, Payment, ServicePlan
from lume_connect.models import ConnectComment, ConnectLike, ConnectPost
from patients.models import Patient, ProfessionalNote, ProfessionalPatientAssignment
from scheduling.models import Appointment, ServicePackage
from team.models import Professional


@override_settings(
    ALLOWED_HOSTS=["testserver", "clinicafisiolume.com.br", "sistema.clinicafisiolume.com.br"],
    WEBSITE_HOSTS=["clinicafisiolume.com.br"],
    SYSTEM_HOSTS=["sistema.clinicafisiolume.com.br"],
    SECURE_SSL_REDIRECT=False,
)
class MobileBootstrapTests(TestCase):
    def create_patient_user(self, username="paciente-mobile", password="Senha@123"):
        patient = Patient.objects.create(full_name=f"Paciente {username}")
        user = get_user_model().objects.create_user(username=username, password=password)
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": patient})
        return user, patient

    def create_professional_user(self, username="prof-mobile", password="Senha@123"):
        professional = Professional.objects.create(
            full_name=f"Profissional {username}",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
        )
        user = get_user_model().objects.create_user(username=username, password=password)
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        return user, professional

    def test_patient_receives_mobile_bootstrap_summary(self):
        user, patient = self.create_patient_user()
        plan = ServicePlan.objects.create(
            name="Plano Mobile",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("400.00"),
            sessions_per_week=2,
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )
        self.client.force_login(user)

        response = self.client.get("/api/v1/mobile/bootstrap/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"]["role"], UserProfile.Role.PATIENT)
        self.assertEqual(response.json()["dashboard"]["memberships"][0]["plan"], "Plano Mobile")

    def test_mobile_token_endpoint_issues_token(self):
        self.create_patient_user(username="token-mobile", password="Senha@123")

        response = self.client.post(
            "/api/v1/mobile/auth/token/",
            {"username": "token-mobile", "password": "Senha@123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    def test_public_host_exposes_mobile_token_health_and_bootstrap(self):
        user, _patient = self.create_patient_user(username="public-mobile", password="Senha@123")

        health = self.client.get("/api/v1/mobile/health/", HTTP_HOST="clinicafisiolume.com.br")
        token_response = self.client.post(
            "/api/v1/mobile/auth/token/",
            {"username": "public-mobile", "password": "Senha@123"},
            HTTP_HOST="clinicafisiolume.com.br",
        )
        token = token_response.json()["token"]
        bootstrap = self.client.get(
            "/api/v1/mobile/bootstrap/",
            HTTP_HOST="clinicafisiolume.com.br",
            HTTP_AUTHORIZATION=f"Token {token}",
        )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(token_response.status_code, 200)
        self.assertEqual(bootstrap.status_code, 200)
        self.assertEqual(bootstrap.json()["profile"]["username"], user.username)

    def test_mobile_login_endpoint_returns_profile_and_features(self):
        self.create_patient_user(username="login-mobile", password="Senha@123")

        response = self.client.post(
            "/api/v1/mobile/auth/login/",
            {"username": "login-mobile", "password": "Senha@123"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("token", payload)
        self.assertEqual(payload["profile"]["role"], UserProfile.Role.PATIENT)
        self.assertIn("meus_pagamentos", payload["features"])

    def test_mobile_bootstrap_accepts_token_authentication(self):
        user, _patient = self.create_patient_user(username="token-bootstrap")
        token = Token.objects.create(user=user)

        response = self.client.get(
            "/api/v1/mobile/bootstrap/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"]["role"], UserProfile.Role.PATIENT)

    def test_mobile_logout_revokes_token(self):
        user, _patient = self.create_patient_user(username="logout-mobile")
        token = Token.objects.create(user=user)

        response = self.client.post(
            "/api/v1/mobile/auth/logout/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_mobile_agenda_returns_only_current_patient_appointments(self):
        user, patient = self.create_patient_user(username="agenda-mobile")
        _other_user, other_patient = self.create_patient_user(username="agenda-outro")
        professional = Professional.objects.create(
            full_name="Profissional Agenda",
            specialty=Professional.Specialty.PILATES,
        )
        starts_at = timezone.now() + timedelta(days=1)
        own_appointment = Appointment.objects.create(
            patient=patient,
            professional=professional,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )
        Appointment.objects.create(
            patient=other_patient,
            professional=professional,
            starts_at=starts_at + timedelta(days=1),
            ends_at=starts_at + timedelta(days=1, hours=1),
        )
        token = Token.objects.create(user=user)

        response = self.client.get(
            "/api/v1/mobile/agenda/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(response.status_code, 200)
        appointments = response.json()["appointments"]
        self.assertEqual([item["id"] for item in appointments], [own_appointment.id])
        self.assertEqual(appointments[0]["patient"]["id"], patient.id)

    def test_mobile_payments_returns_only_current_patient_payments(self):
        user, patient = self.create_patient_user(username="pagamentos-mobile")
        _other_user, other_patient = self.create_patient_user(username="pagamentos-outro")
        plan = ServicePlan.objects.create(
            name="Plano Pagamentos",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("450.00"),
            sessions_per_week=2,
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        other_membership = Membership.objects.create(patient=other_patient, plan=plan, due_day=12)
        own_payment = Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 7, 1),
            due_date=date(2026, 7, 10),
            amount=Decimal("450.00"),
        )
        Payment.objects.create(
            membership=other_membership,
            reference_month=date(2026, 7, 1),
            due_date=date(2026, 7, 12),
            amount=Decimal("450.00"),
        )
        token = Token.objects.create(user=user)

        response = self.client.get(
            "/api/v1/mobile/payments/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["payments"]], [own_payment.id])

    def test_mobile_credits_returns_patient_packages(self):
        user, patient = self.create_patient_user(username="creditos-mobile")
        plan = ServicePlan.objects.create(
            name="Plano Creditos",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("500.00"),
            sessions_per_week=3,
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        package = ServicePackage.objects.create(
            membership=membership,
            total_sessions=10,
            used_sessions=4,
        )
        token = Token.objects.create(user=user)

        response = self.client.get(
            "/api/v1/mobile/credits/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["packages"][0]["id"], package.id)
        self.assertEqual(response.json()["package_credits"]["remaining"], 6)

    def test_professional_notes_endpoint_hides_body_and_denies_patient_role(self):
        patient_user, patient = self.create_patient_user(username="nota-paciente")
        professional_user, professional = self.create_professional_user(username="nota-profissional")
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        note = ProfessionalNote.objects.create(
            patient=patient,
            professional=professional,
            title="Evolucao sensivel",
            body="Conteudo clinico detalhado que nao deve ir na listagem.",
        )
        patient_token = Token.objects.create(user=patient_user)
        professional_token = Token.objects.create(user=professional_user)

        patient_response = self.client.get(
            "/api/v1/mobile/professional-notes/",
            HTTP_AUTHORIZATION=f"Token {patient_token.key}",
        )
        professional_response = self.client.get(
            "/api/v1/mobile/professional-notes/",
            HTTP_AUTHORIZATION=f"Token {professional_token.key}",
        )

        self.assertEqual(patient_response.status_code, 200)
        self.assertEqual(patient_response.json()["notes"], [])
        self.assertEqual(professional_response.status_code, 200)
        self.assertEqual(professional_response.json()["notes"][0]["id"], note.id)
        self.assertNotIn("body", professional_response.json()["notes"][0])

    def test_mobile_connect_feed_create_like_and_comment(self):
        user, _patient = self.create_patient_user(username="connect-mobile")
        other_user, _other_patient = self.create_patient_user(username="connect-outro")
        post = ConnectPost.objects.create(author=other_user, content="Bem-vindos ao Connect")
        ConnectComment.objects.create(post=post, author=other_user, content="Primeiro comentario")
        token = Token.objects.create(user=user)

        feed_response = self.client.get(
            "/api/v1/mobile/connect/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        create_response = self.client.post(
            "/api/v1/mobile/connect/",
            {"content": "Treino leve feito hoje"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        like_response = self.client.post(
            f"/api/v1/mobile/connect/{post.pk}/like/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        comment_response = self.client.post(
            f"/api/v1/mobile/connect/{post.pk}/comments/",
            {"content": "Gostei muito"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(feed_response.status_code, 200)
        self.assertEqual(feed_response.json()["posts"][0]["id"], post.id)
        self.assertEqual(create_response.status_code, 201)
        self.assertTrue(ConnectPost.objects.filter(author=user, content__icontains="Treino leve").exists())
        self.assertEqual(like_response.status_code, 200)
        self.assertTrue(ConnectLike.objects.filter(post=post, user=user).exists())
        self.assertEqual(comment_response.status_code, 201)
        self.assertTrue(ConnectComment.objects.filter(post=post, author=user, content="Gostei muito").exists())
