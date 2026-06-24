from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Expense, ExpenseCategory, Membership, Payment, ServicePlan
from patients.models import Patient
from scheduling.models import Appointment
from team.models import Professional


class ReportsAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="gestor", password="Senha@123")
        UserProfile.objects.update_or_create(user=self.user, defaults={"role": UserProfile.Role.MANAGEMENT})

    def test_management_can_access_reports_with_period_summary(self):
        patient = Patient.objects.create(full_name="Paciente Relatorio")
        professional = Professional.objects.create(full_name="Dra. Relatorio", specialty=Professional.Specialty.PILATES)
        plan = ServicePlan.objects.create(
            name="Plano Relatorio",
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
            status=Payment.Status.PAID,
            paid_at=date(2026, 6, 10),
        )
        category = ExpenseCategory.objects.get(name="Aluguel")
        Expense.objects.create(
            description="Aluguel teste",
            category=category,
            kind=Expense.Kind.FIXED,
            due_date=date(2026, 6, 5),
            amount=Decimal("100.00"),
            status=Expense.Status.OPEN,
        )
        start = timezone.make_aware(datetime.combine(date(2026, 6, 12), time(9, 0)))
        Appointment.objects.create(
            patient=patient,
            professional=professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            status=Appointment.Status.COMPLETED,
            completed_at=start,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("reports:dashboard"), {"start": "2026-06-01", "end": "2026-06-30"})

        self.assertContains(response, "Relatorios")
        self.assertContains(response, "R$ 400,00")
        self.assertContains(response, "Dra. Relatorio")

    def test_patient_cannot_access_reports(self):
        patient = Patient.objects.create(full_name="Paciente Sem Relatorio")
        user = get_user_model().objects.create_user(username="paciente-relatorio", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": patient})
        self.client.force_login(user)

        response = self.client.get(reverse("reports:dashboard"))

        self.assertEqual(response.status_code, 302)
