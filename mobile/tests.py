from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token

from accounts.models import UserProfile
from billing.models import Membership, Payment, ServicePlan
from patients.models import Patient


class MobileBootstrapTests(TestCase):
    def create_patient_user(self, username="paciente-mobile", password="Senha@123"):
        patient = Patient.objects.create(full_name=f"Paciente {username}")
        user = get_user_model().objects.create_user(username=username, password=password)
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": patient})
        return user, patient

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

    def test_mobile_bootstrap_accepts_token_authentication(self):
        user, _patient = self.create_patient_user(username="token-bootstrap")
        token = Token.objects.create(user=user)

        response = self.client.get(
            "/api/v1/mobile/bootstrap/",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"]["role"], UserProfile.Role.PATIENT)
