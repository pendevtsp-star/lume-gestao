from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from billing.models import Membership, Payment, ServicePlan
from patients.models import Patient


class BillingModelTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(full_name="Paciente Teste")
        self.plan = ServicePlan.objects.create(
            name="Pilates Teste",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("400.00"),
            sessions_per_week=2,
        )

    def test_plan_requires_positive_price(self):
        plan = ServicePlan(
            name="Plano invalido",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("0.00"),
            sessions_per_week=2,
        )

        with self.assertRaises(ValidationError):
            plan.full_clean()

    def test_membership_due_day_must_be_safe_for_all_months(self):
        membership = Membership(
            patient=self.patient,
            plan=self.plan,
            due_day=31,
            discount_amount=Decimal("0.00"),
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_membership_monthly_amount_applies_discount(self):
        membership = Membership(
            patient=self.patient,
            plan=self.plan,
            due_day=10,
            discount_amount=Decimal("50.00"),
        )

        self.assertEqual(membership.monthly_amount, Decimal("350.00"))

    def test_payment_paid_requires_paid_date(self):
        membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        payment = Payment(
            membership=membership,
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PAID,
        )

        with self.assertRaises(ValidationError):
            payment.full_clean()

    def test_payment_reference_month_must_be_first_day(self):
        membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        payment = Payment(
            membership=membership,
            reference_month=date(2026, 6, 15),
            due_date=date(2026, 6, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )

        with self.assertRaises(ValidationError):
            payment.full_clean()
