from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Membership, Payment, ServicePlan
from checkout.models import CheckoutOrder, CheckoutPaymentEvent
from patients.models import Patient
from scheduling.models import ServicePackage


CHECKOUT_TEST_SETTINGS = {
    "CHECKOUT_ENABLED": True,
    "CHECKOUT_PUBLIC_ENABLED": True,
    "CHECKOUT_PATIENT_ENABLED": True,
    "CHECKOUT_WEBHOOK_ENABLED": True,
    "CHECKOUT_PAYMENT_PROVIDER": "asaas",
    "ASAAS_DRY_RUN": True,
    "ASAAS_WEBHOOK_TOKEN": "token-checkout",
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
}


@override_settings(**CHECKOUT_TEST_SETTINGS)
class CheckoutPublicTests(TestCase):
    def setUp(self):
        self.plan = ServicePlan.objects.create(
            name="Pilates Online",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("320.00"),
            sessions_per_week=2,
            show_on_website=True,
            active=True,
        )

    def test_public_checkout_creates_pending_order_without_patient_before_webhook(self):
        response = self.client.post(
            reverse("checkout:plan", args=[self.plan.pk]),
            {
                "full_name": "Maria Checkout",
                "cpf": "12345678901",
                "birth_date": "1990-01-10",
                "phone": "11999990000",
                "email": "maria.checkout@example.com",
                "accept_terms": "on",
            },
        )

        order = CheckoutOrder.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(order.status, CheckoutOrder.Status.PENDING)
        self.assertEqual(order.amount, Decimal("320.00"))
        self.assertFalse(Patient.objects.filter(email="maria.checkout@example.com").exists())

    def test_webhook_confirms_plan_purchase_and_is_idempotent(self):
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            plan=self.plan,
            customer_name="Maria Confirmada",
            customer_document="12345678901",
            customer_birth_date=date(1990, 1, 10),
            customer_phone="11999990000",
            customer_email="maria.confirmada@example.com",
            amount=self.plan.monthly_price,
            provider_payment_id="pay_123",
        )
        payload = {
            "id": "evt_checkout_123",
            "event": "PAYMENT_CONFIRMED",
            "payment": {
                "id": "pay_123",
                "externalReference": order.external_reference,
                "value": "320.00",
                "billingType": "PIX",
                "confirmedDate": "2026-06-29",
            },
        }

        first = self.client.post(
            reverse("checkout:asaas_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="token-checkout",
        )
        second = self.client.post(
            reverse("checkout:asaas_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="token-checkout",
        )

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["created"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        order.refresh_from_db()
        patient = Patient.objects.get(email="maria.confirmada@example.com")
        self.assertEqual(order.status, CheckoutOrder.Status.PAID)
        self.assertEqual(order.created_patient, patient)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(ServicePackage.objects.count(), 1)
        self.assertEqual(CheckoutPaymentEvent.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(patient.user_profile.must_change_password)
        self.assertIsNotNone(patient.user_profile.terms_accepted_at)


@override_settings(**CHECKOUT_TEST_SETTINGS)
class CheckoutPatientPaymentTests(TestCase):
    def test_patient_can_start_pending_payment_checkout_and_webhook_marks_paid(self):
        patient = Patient.objects.create(full_name="Paciente Pagante", email="pagante@example.com")
        user = get_user_model().objects.create_user(username="pagante", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": patient})
        plan = ServicePlan.objects.create(
            name="Plano Mensal",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("300.00"),
            sessions_per_week=2,
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=timezone.localdate().replace(day=1),
            due_date=timezone.localdate(),
            amount=Decimal("300.00"),
            status=Payment.Status.PENDING,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("checkout:payment_start", args=[payment.pk]))

        self.assertEqual(response.status_code, 302)
        order = CheckoutOrder.objects.get(payment=payment)
        payload = {
            "id": "evt_payment_123",
            "event": "PAYMENT_RECEIVED",
            "payment": {
                "id": order.provider_payment_id,
                "externalReference": order.external_reference,
                "value": "300.00",
                "billingType": "PIX",
                "paymentDate": "2026-06-29",
            },
        }
        webhook = self.client.post(
            reverse("checkout:asaas_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN="token-checkout",
        )

        self.assertEqual(webhook.status_code, 200)
        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.method, Payment.Method.PIX)
        self.assertEqual(order.status, CheckoutOrder.Status.PAID)
