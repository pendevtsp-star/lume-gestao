from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Membership, Payment, ServicePlan
from checkout.models import CheckoutMerchantAccount, CheckoutOrder, CheckoutPaymentEvent
from checkout.services import start_checkout_order
from core.integrations.http import IntegrationError
from patients.models import Patient
from scheduling.models import ServicePackage


CHECKOUT_TEST_SETTINGS = {
    "CHECKOUT_ENABLED": True,
    "CHECKOUT_PUBLIC_ENABLED": True,
    "CHECKOUT_PATIENT_ENABLED": True,
    "CHECKOUT_WEBHOOK_ENABLED": True,
    "CHECKOUT_PAYMENT_PROVIDER": "asaas",
    "CHECKOUT_REQUIRE_MERCHANT_ACCOUNT": False,
    "ASAAS_DRY_RUN": True,
    "ASAAS_WEBHOOK_TOKEN": "token-checkout",
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
}

CHECKOUT_SANDBOX_TEST_SETTINGS = {
    **CHECKOUT_TEST_SETTINGS,
    "ASAAS_DRY_RUN": False,
    "ASAAS_BASE_URL": "https://api-sandbox.asaas.com/v3",
    "ASAAS_API_KEY": "sandbox_key_segura",
    "ASAAS_WEBHOOK_TOKEN": "token-sandbox",
    "CHECKOUT_REQUIRE_MERCHANT_ACCOUNT": True,
}


@override_settings(**CHECKOUT_TEST_SETTINGS, ASAAS_API_KEY="sk_test_segura", ASAAS_BASE_URL="https://api-sandbox.asaas.com/v3")
class CheckoutDashboardTests(TestCase):
    def test_management_can_view_asaas_checkout_dashboard_without_secret_leak(self):
        user = get_user_model().objects.create_user(username="gestao-checkout", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.PAYMENT,
            customer_name="Paciente Dashboard",
            customer_email="dashboard@example.com",
            amount=Decimal("120.00"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("checkout:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Checkout Asaas")
        self.assertContains(response, "Dry-run local")
        self.assertContains(response, "API Asaas")
        self.assertContains(response, reverse("checkout:asaas_webhook"))
        self.assertContains(response, "Conta recebedora da clinica")
        self.assertContains(response, "Cadastro comercial ainda nao iniciado")
        self.assertNotContains(response, "sk_test_segura")
        self.assertNotContains(response, "token-checkout")

    def test_dashboard_shows_merchant_account_without_receiver_identifier(self):
        user = get_user_model().objects.create_user(username="gestao-recebedor", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        CheckoutMerchantAccount.objects.create(
            provider=CheckoutMerchantAccount.Provider.ASAAS,
            account_type=CheckoutMerchantAccount.AccountType.SUBACCOUNT,
            status=CheckoutMerchantAccount.Status.ACTIVE,
            trade_name="Clinica Lume",
            provider_wallet_id="wallet_sandbox_123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("checkout:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clinica Lume")
        self.assertContains(response, "Subconta comercial")
        self.assertContains(response, "Recebimento: configurado")
        self.assertNotContains(response, "wallet_sandbox_123")


@override_settings(**CHECKOUT_TEST_SETTINGS)
class CheckoutMerchantAccountTests(TestCase):
    def setUp(self):
        self.management_user = get_user_model().objects.create_user(username="gestao-merchant", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=self.management_user,
            defaults={"role": UserProfile.Role.MANAGEMENT},
        )

    def test_start_checkout_order_links_active_merchant_account(self):
        merchant = CheckoutMerchantAccount.objects.create(
            provider=CheckoutMerchantAccount.Provider.ASAAS,
            account_type=CheckoutMerchantAccount.AccountType.SUBACCOUNT,
            status=CheckoutMerchantAccount.Status.ACTIVE,
            trade_name="Clinica Lume",
            provider_wallet_id="wallet_sandbox_123",
        )
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            customer_name="Paciente Recebedor",
            customer_email="recebedor@example.com",
            amount=Decimal("120.00"),
        )

        start_checkout_order(order)

        order.refresh_from_db()
        self.assertEqual(order.merchant_account, merchant)
        self.assertEqual(order.status, CheckoutOrder.Status.PENDING)

    @override_settings(ASAAS_DRY_RUN=False, CHECKOUT_REQUIRE_MERCHANT_ACCOUNT=True)
    def test_remote_checkout_requires_ready_merchant_account_in_commercial_mode(self):
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            customer_name="Paciente Bloqueado",
            customer_email="bloqueado@example.com",
            amount=Decimal("120.00"),
        )

        with self.assertRaises(IntegrationError):
            start_checkout_order(order)

    def test_management_can_create_merchant_onboarding_draft(self):
        self.client.force_login(self.management_user)

        response = self.client.post(
            reverse("checkout:merchant_onboarding"),
            self.valid_merchant_payload(save_draft="1"),
            follow=True,
        )

        merchant = CheckoutMerchantAccount.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cadastro financeiro salvo como rascunho.")
        self.assertContains(response, "Clinica de Teste")
        self.assertEqual(merchant.status, CheckoutMerchantAccount.Status.DRAFT)
        self.assertEqual(merchant.document, "12345678000199")
        self.assertEqual(merchant.postal_code, "30130010")
        self.assertEqual(merchant.state, "MG")
        self.assertEqual(merchant.account_type, CheckoutMerchantAccount.AccountType.SUBACCOUNT)

    def test_management_can_mark_merchant_onboarding_for_review(self):
        self.client.force_login(self.management_user)

        response = self.client.post(
            reverse("checkout:merchant_onboarding"),
            self.valid_merchant_payload(submit_for_review="1"),
            follow=True,
        )

        merchant = CheckoutMerchantAccount.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(merchant.status, CheckoutMerchantAccount.Status.PENDING_PROVIDER)
        self.assertIsNotNone(merchant.onboarding_started_at)
        self.assertContains(response, "marcado para analise")

    def test_merchant_onboarding_validates_document_and_postal_code(self):
        self.client.force_login(self.management_user)
        payload = self.valid_merchant_payload(save_draft="1")
        payload["document"] = "123"
        payload["postal_code"] = "301"

        response = self.client.post(reverse("checkout:merchant_onboarding"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CPF com 11 digitos ou CNPJ com 14 digitos")
        self.assertContains(response, "CEP com 8 digitos")
        self.assertFalse(CheckoutMerchantAccount.objects.exists())

    def valid_merchant_payload(self, **extra):
        payload = {
            "legal_name": "Clinica de Teste LTDA",
            "trade_name": "Clinica de Teste",
            "company_type": CheckoutMerchantAccount.CompanyType.LIMITED,
            "responsible_name": "Maria Financeira",
            "document": "12.345.678/0001-99",
            "birth_date": "",
            "monthly_income": "15000.00",
            "email": "financeiro@example.com",
            "phone": "(31) 99999-0000",
            "address": "Rua da Clinica",
            "address_number": "120",
            "complement": "Sala 2",
            "neighborhood": "Centro",
            "city": "Belo Horizonte",
            "state": "mg",
            "postal_code": "30130-010",
            "notes": "Cadastro de homologacao.",
        }
        payload.update(extra)
        return payload


@override_settings(**CHECKOUT_TEST_SETTINGS)
class CheckoutDryRunHomologationCommandTests(TestCase):
    def test_homologation_command_runs_full_flow_without_persisting_data(self):
        output = StringIO()

        call_command("homologate_checkout_dry_run", stdout=output)

        result = output.getvalue()
        self.assertIn("Homologacao Checkout Asaas dry-run concluida.", result)
        self.assertIn("Fluxo 1: compra publica de plano confirmada", result)
        self.assertIn("Fluxo 2: mensalidade pendente paga", result)
        self.assertIn("Dados temporarios descartados automaticamente.", result)
        self.assertFalse(CheckoutOrder.objects.filter(customer_name__icontains="Homologacao Asaas").exists())
        self.assertFalse(ServicePlan.objects.filter(name__icontains="Homologacao Checkout Asaas").exists())

    @override_settings(ASAAS_DRY_RUN=False)
    def test_homologation_command_refuses_real_payment_mode(self):
        with self.assertRaises(CommandError):
            call_command("homologate_checkout_dry_run", stdout=StringIO())


@override_settings(**CHECKOUT_SANDBOX_TEST_SETTINGS)
class CheckoutSandboxHomologationCommandTests(TestCase):
    def test_sandbox_command_creates_remote_charges_with_mocked_asaas_and_discards_local_data(self):
        output = StringIO()
        self.create_ready_merchant_account()

        with patch("checkout.services.post_json", side_effect=self.fake_asaas_post_json):
            call_command("homologate_checkout_sandbox", stdout=output)

        result = output.getvalue()
        self.assertIn("Homologacao sandbox Asaas concluida.", result)
        self.assertIn("Webhook local com token: validado.", result)
        self.assertIn("Dados locais descartados automaticamente.", result)
        self.assertFalse(CheckoutOrder.objects.filter(customer_name__icontains="Sandbox").exists())
        self.assertFalse(ServicePlan.objects.filter(name__icontains="Sandbox Checkout Asaas").exists())

    @override_settings(ASAAS_BASE_URL="https://api.asaas.com/v3")
    def test_sandbox_command_refuses_production_base_url(self):
        with self.assertRaises(CommandError):
            call_command("homologate_checkout_sandbox", stdout=StringIO())

    @override_settings(ASAAS_DRY_RUN=True)
    def test_sandbox_command_refuses_dry_run_mode(self):
        with self.assertRaises(CommandError):
            call_command("homologate_checkout_sandbox", stdout=StringIO())

    def test_sandbox_command_refuses_missing_ready_merchant_account(self):
        with self.assertRaises(CommandError):
            call_command("homologate_checkout_sandbox", stdout=StringIO())

    def create_ready_merchant_account(self):
        return CheckoutMerchantAccount.objects.create(
            provider=CheckoutMerchantAccount.Provider.ASAAS,
            account_type=CheckoutMerchantAccount.AccountType.SUBACCOUNT,
            status=CheckoutMerchantAccount.Status.ACTIVE,
            trade_name="Clinica Sandbox",
            provider_wallet_id="wallet_sandbox_123",
        )

    def fake_asaas_post_json(self, url, payload, headers=None, timeout=15):
        if url.endswith("/customers"):
            return {"id": f"cus_sandbox_{payload['externalReference'][-8:]}"}
        if url.endswith("/payments"):
            return {
                "id": f"pay_sandbox_{payload['externalReference'][-8:]}",
                "customer": payload["customer"],
                "invoiceUrl": f"https://sandbox.asaas.com/i/{payload['externalReference']}",
                "externalReference": payload["externalReference"],
            }
        raise AssertionError(f"URL inesperada no mock Asaas: {url}")


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

    def test_public_checkout_reuses_recent_pending_order_for_same_buyer(self):
        payload = {
            "full_name": "Maria Checkout",
            "cpf": "12345678901",
            "birth_date": "1990-01-10",
            "phone": "11999990000",
            "email": "maria.checkout@example.com",
            "accept_terms": "on",
        }

        first = self.client.post(reverse("checkout:plan", args=[self.plan.pk]), payload)
        second = self.client.post(reverse("checkout:plan", args=[self.plan.pk]), payload)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(CheckoutOrder.objects.count(), 1)

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

    def test_patient_payment_reuses_pending_checkout_order(self):
        patient = Patient.objects.create(full_name="Paciente Reuso", email="reuso@example.com")
        user = get_user_model().objects.create_user(username="reuso", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": patient})
        plan = ServicePlan.objects.create(
            name="Plano Reuso",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("280.00"),
            sessions_per_week=2,
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=timezone.localdate().replace(day=1),
            due_date=timezone.localdate(),
            amount=Decimal("280.00"),
            status=Payment.Status.PENDING,
        )
        self.client.force_login(user)

        self.client.post(reverse("checkout:payment_start", args=[payment.pk]))
        self.client.post(reverse("checkout:payment_start", args=[payment.pk]))

        self.assertEqual(CheckoutOrder.objects.filter(payment=payment).count(), 1)


@override_settings(**CHECKOUT_TEST_SETTINGS)
class CheckoutOrderActionTests(TestCase):
    def setUp(self):
        self.management_user = get_user_model().objects.create_user(username="gestao-acoes", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=self.management_user,
            defaults={"role": UserProfile.Role.MANAGEMENT},
        )
        self.client.force_login(self.management_user)

    def test_management_can_cancel_pending_order(self):
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            status=CheckoutOrder.Status.PENDING,
            customer_name="Paciente Cancelar",
            customer_email="cancelar@example.com",
            amount=Decimal("200.00"),
        )

        response = self.client.post(reverse("checkout:order_action", args=[order.pk, "cancel"]), follow=True)

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, CheckoutOrder.Status.CANCELED)
        self.assertIn("Cancelado manualmente", order.notes)

    def test_management_can_expire_pending_order(self):
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            status=CheckoutOrder.Status.PENDING,
            customer_name="Paciente Expirar",
            customer_email="expirar@example.com",
            amount=Decimal("200.00"),
        )

        response = self.client.post(reverse("checkout:order_action", args=[order.pk, "expire"]), follow=True)

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, CheckoutOrder.Status.EXPIRED)
        self.assertIn("Expirado manualmente", order.notes)

    def test_management_cannot_cancel_paid_order(self):
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            status=CheckoutOrder.Status.PAID,
            customer_name="Paciente Pago",
            customer_email="pago@example.com",
            amount=Decimal("200.00"),
        )

        response = self.client.post(reverse("checkout:order_action", args=[order.pk, "cancel"]), follow=True)

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, CheckoutOrder.Status.PAID)

    def test_management_can_generate_link_for_failed_order(self):
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            status=CheckoutOrder.Status.FAILED,
            customer_name="Paciente Link",
            customer_email="link@example.com",
            amount=Decimal("200.00"),
        )

        response = self.client.post(reverse("checkout:order_action", args=[order.pk, "retry"]), follow=True)

        order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order.status, CheckoutOrder.Status.PENDING)
        self.assertTrue(order.checkout_url)
