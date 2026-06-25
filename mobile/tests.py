from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import UserProfile
from billing.models import Membership, Payment, ServicePlan
from patients.models import Patient


class MobileBootstrapTests(TestCase):
    def test_patient_receives_mobile_bootstrap_summary(self):
        patient = Patient.objects.create(full_name="Paciente Mobile")
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
        user = get_user_model().objects.create_user(username="paciente-mobile", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": patient})
        self.client.force_login(user)

        response = self.client.get("/api/v1/mobile/bootstrap/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["profile"]["role"], UserProfile.Role.PATIENT)
        self.assertEqual(response.json()["dashboard"]["memberships"][0]["plan"], "Plano Mobile")
