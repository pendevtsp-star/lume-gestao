from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from billing.forms import PaymentForm
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

    def test_payment_form_uses_month_and_year_for_reference(self):
        membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)

        form = PaymentForm(
            data={
                "membership": membership.pk,
                "item_type": Payment.ItemType.MEMBERSHIP,
                "reference_month_number": "7",
                "reference_year": "2026",
                "due_date": "2026-07-10",
                "amount": "400.00",
                "status": Payment.Status.PENDING,
                "method": Payment.Method.MANUAL,
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        payment = form.save()
        self.assertEqual(payment.reference_month, date(2026, 7, 1))
        self.assertEqual(payment.patient, self.patient)
        self.assertEqual(payment.description, self.plan.name)

    def test_payment_form_accepts_standalone_service_payment(self):
        form = PaymentForm(
            data={
                "patient": self.patient.pk,
                "item_type": Payment.ItemType.SERVICE,
                "description": "Massagem avulsa",
                "reference_month_number": "7",
                "reference_year": "2026",
                "due_date": "2026-07-10",
                "amount": "R$ 150,00",
                "status": Payment.Status.PENDING,
                "method": Payment.Method.PIX,
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        payment = form.save()
        self.assertIsNone(payment.membership)
        self.assertEqual(payment.patient, self.patient)
        self.assertEqual(payment.amount, Decimal("150.00"))
        self.assertEqual(payment.item_display, "Massagem avulsa")

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

    def test_payment_receive_marks_pending_payment_as_paid(self):
        user = get_user_model().objects.create_user(username="financeiro-recebe", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.ADMINISTRATION})
        membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("billing:payment_receive", args=[payment.pk]),
            {
                "amount": "400.00",
                "method": Payment.Method.CASH,
                "paid_at": "2026-06-12",
                "notes": "Recebido no balcão.",
            },
        )

        self.assertRedirects(response, reverse("billing:payments"))
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.method, Payment.Method.CASH)
        self.assertEqual(payment.paid_at, date(2026, 6, 12))

    def test_payment_quick_receive_lists_only_open_payments(self):
        user = get_user_model().objects.create_user(username="financeiro-recebimento-rapido", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.ADMINISTRATION})
        membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        pending = Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )
        Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 7, 1),
            due_date=date(2026, 7, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PAID,
            paid_at=date(2026, 7, 10),
        )
        Payment.objects.create(
            patient=self.patient,
            item_type=Payment.ItemType.SERVICE,
            description="Massagem avulsa",
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 12),
            amount=Decimal("150.00"),
            status=Payment.Status.PENDING,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("billing:payment_quick_receive"), {"q": "Paciente"})

        self.assertContains(response, "Receber mensalidade")
        self.assertContains(response, reverse("billing:payment_receive", args=[pending.pk]))
        self.assertNotContains(response, "07/2026")
        self.assertNotContains(response, "Massagem avulsa")

    def test_expense_delete_deactivate_cancels_expense_and_removes_from_totals(self):
        user = get_user_model().objects.create_user(username="financeiro-exclui-despesa", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.ADMINISTRATION})
        category = ExpenseCategory.objects.get(name="Aluguel")
        expense = Expense.objects.create(
            description="Despesa duplicada",
            category=category,
            kind=Expense.Kind.FIXED,
            due_date=date(2026, 6, 5),
            amount=Decimal("1000.00"),
            status=Expense.Status.OPEN,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("billing:expense_delete", args=[expense.pk]),
            {"delete_action": "deactivate"},
        )

        self.assertRedirects(response, reverse("billing:expenses"))
        expense.refresh_from_db()
        self.assertEqual(expense.status, Expense.Status.CANCELED)
        list_response = self.client.get(reverse("billing:expenses"))
        self.assertContains(list_response, "R$ 0,00")

    def test_membership_delete_deactivate_cancels_pending_payment(self):
        user = get_user_model().objects.create_user(username="financeiro-exclui-mensalidade", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("billing:membership_delete", args=[membership.pk]),
            {"delete_action": "deactivate"},
        )

        self.assertRedirects(response, reverse("billing:memberships"))
        membership.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(membership.status, Membership.Status.CANCELED)
        self.assertEqual(payment.status, Payment.Status.CANCELED)

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
