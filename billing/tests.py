from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from billing.models import Expense, ExpenseCategory, Membership, Payment, ServicePlan
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

    def test_patient_can_have_multiple_active_memberships_for_different_services(self):
        other_plan = ServicePlan.objects.create(
            name="Massagem avulsa",
            category=ServicePlan.Category.MASSAGE,
            plan_type=ServicePlan.PlanType.SINGLE,
            monthly_price=Decimal("120.00"),
            sessions_per_week=1,
            included_sessions=1,
        )
        Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        membership = Membership(patient=self.patient, plan=other_plan, due_day=15)

        membership.full_clean()
        membership.save()

        self.assertEqual(Membership.objects.filter(patient=self.patient, status=Membership.Status.ACTIVE).count(), 2)

    def test_patient_cannot_have_duplicate_active_membership_for_same_plan(self):
        Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        duplicate = Membership(patient=self.patient, plan=self.plan, due_day=15)

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_single_service_plan_uses_one_included_session(self):
        plan = ServicePlan(
            name="Sessao avulsa",
            category=ServicePlan.Category.PHYSIOTHERAPY,
            plan_type=ServicePlan.PlanType.SINGLE,
            monthly_price=Decimal("180.00"),
            sessions_per_week=3,
            included_sessions=8,
        )

        plan.full_clean()

        self.assertEqual(plan.sessions_per_week, 1)
        self.assertEqual(plan.default_total_sessions, 1)

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

    def test_expense_category_and_kind_are_editable_structures(self):
        category = ExpenseCategory.objects.create(name="Marketing", kind=ExpenseCategory.Kind.VARIABLE)
        expense = Expense(
            description="Campanha local",
            category=category,
            kind=Expense.Kind.VARIABLE,
            due_date=date(2026, 6, 20),
            amount=Decimal("250.00"),
            status=Expense.Status.OPEN,
        )

        expense.full_clean()

        self.assertEqual(str(category), "Marketing")

    def test_expense_list_filters_by_kind_and_summarizes_values(self):
        user = get_user_model().objects.create_user(username="financeiro", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.ADMINISTRATION})
        fixed = ExpenseCategory.objects.get(name="Aluguel")
        variable = ExpenseCategory.objects.get(name="Insumos")
        Expense.objects.create(
            description="Aluguel sala",
            category=fixed,
            kind=Expense.Kind.FIXED,
            due_date=date(2026, 6, 5),
            amount=Decimal("1000.00"),
            status=Expense.Status.OPEN,
        )
        Expense.objects.create(
            description="Faixas elasticas",
            category=variable,
            kind=Expense.Kind.VARIABLE,
            due_date=date(2026, 6, 8),
            amount=Decimal("100.00"),
            status=Expense.Status.PAID,
            paid_at=date(2026, 6, 8),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("billing:expenses"), {"kind": Expense.Kind.FIXED})

        self.assertContains(response, "Aluguel sala")
        self.assertNotContains(response, "Faixas elasticas")
        self.assertContains(response, "R$ 1000,00")

    def test_plan_delete_removes_unused_plan(self):
        user = get_user_model().objects.create_user(username="gerencia-exclui-plano", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        plan = ServicePlan.objects.create(
            name="Plano sem uso",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("200.00"),
            sessions_per_week=1,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("billing:plan_delete", args=[plan.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ServicePlan.objects.filter(pk=plan.pk).exists())

    def test_plan_delete_deactivates_plan_with_history(self):
        user = get_user_model().objects.create_user(username="gerencia-desativa-plano", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        self.client.force_login(user)

        response = self.client.post(reverse("billing:plan_delete", args=[self.plan.pk]))

        self.assertEqual(response.status_code, 302)
        self.plan.refresh_from_db()
        self.assertFalse(self.plan.active)

    def test_patient_cannot_access_finance_api(self):
        user = get_user_model().objects.create_user(username="paciente-finance-api", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient})
        self.client.force_login(user)

        response = self.client.get("/api/v1/payments/")

        self.assertEqual(response.status_code, 403)
