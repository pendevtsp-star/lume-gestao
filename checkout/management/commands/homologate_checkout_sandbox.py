from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import RequestFactory
from django.utils import timezone

from billing.models import Membership, Payment, ServicePlan
from checkout.models import CheckoutOrder
from checkout.providers import configured_secret, get_active_merchant_account
from checkout.services import parse_asaas_payload, record_asaas_checkout_webhook, start_checkout_order
from patients.models import Patient


class Command(BaseCommand):
    help = "Homologa o checkout usando a API sandbox real do Asaas, sem cobranca real."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-data",
            action="store_true",
            help="Mantem dados locais de homologacao. Por padrao, os dados locais sao descartados.",
        )

    def handle(self, *args, **options):
        self.validate_safe_settings()
        keep_data = options["keep_data"]

        with transaction.atomic():
            suffix = uuid4().hex[:10]
            public_order = self.create_public_plan_order(suffix)
            payment_order = self.create_patient_payment_order(suffix)

            public_result = start_checkout_order(public_order)
            payment_result = start_checkout_order(payment_order)
            self.validate_remote_result(public_order, public_result, "compra publica")
            self.validate_remote_result(payment_order, payment_result, "mensalidade")
            self.validate_webhook_token(public_order, f"evt_sandbox_token_{suffix}")
            self.validate_webhook_business_flow(payment_order, f"evt_sandbox_flow_{suffix}")

            self.stdout.write(self.style.SUCCESS("Homologacao sandbox Asaas concluida."))
            self.stdout.write("Ambiente: api-sandbox.asaas.com | ASAAS_DRY_RUN=False")
            self.stdout.write(f"Cobranca sandbox compra publica: {public_order.provider_payment_id}")
            self.stdout.write(f"Cobranca sandbox mensalidade: {payment_order.provider_payment_id}")
            self.stdout.write("Webhook local com token: validado.")
            self.stdout.write("Webhook de baixa financeira: validado em transacao local.")

            if keep_data:
                self.stdout.write(self.style.WARNING("Dados locais mantidos por --keep-data."))
            else:
                transaction.set_rollback(True)
                self.stdout.write("Dados locais descartados automaticamente.")

            self.stdout.write(
                self.style.WARNING(
                    "Observacao: as cobrancas criadas ficam apenas no sandbox do Asaas e nao geram custo real."
                )
            )

    def validate_safe_settings(self):
        if settings.CHECKOUT_PAYMENT_PROVIDER != CheckoutOrder.Provider.ASAAS:
            raise CommandError("Esta homologacao esta preparada apenas para CHECKOUT_PAYMENT_PROVIDER=asaas.")
        if settings.ASAAS_DRY_RUN:
            raise CommandError("Defina ASAAS_DRY_RUN=False para testar a API sandbox real do Asaas.")
        if "api-sandbox.asaas.com" not in settings.ASAAS_BASE_URL.lower():
            raise CommandError("Sandbox bloqueado: ASAAS_BASE_URL deve apontar para https://api-sandbox.asaas.com/v3.")
        if not configured_secret(settings.ASAAS_API_KEY):
            raise CommandError("Configure ASAAS_API_KEY com uma chave sandbox valida antes desta homologacao.")
        if not configured_secret(settings.ASAAS_WEBHOOK_TOKEN):
            raise CommandError("Configure ASAAS_WEBHOOK_TOKEN com um token forte para validar webhooks.")
        if settings.CHECKOUT_REQUIRE_MERCHANT_ACCOUNT:
            merchant_account = get_active_merchant_account()
            if not (merchant_account and merchant_account.is_ready):
                raise CommandError(
                    "Cadastre uma conta recebedora ativa antes da homologacao sandbox em modo comercial."
                )

        required_flags = {
            "CHECKOUT_ENABLED": settings.CHECKOUT_ENABLED,
            "CHECKOUT_PUBLIC_ENABLED": settings.CHECKOUT_PUBLIC_ENABLED,
            "CHECKOUT_PATIENT_ENABLED": settings.CHECKOUT_PATIENT_ENABLED,
            "CHECKOUT_WEBHOOK_ENABLED": settings.CHECKOUT_WEBHOOK_ENABLED,
        }
        disabled = [name for name, enabled in required_flags.items() if not enabled]
        if disabled:
            raise CommandError("Ative as flags de checkout para homologacao sandbox: " + ", ".join(disabled))

    def create_plan(self, suffix):
        return ServicePlan.objects.create(
            name=f"Sandbox Checkout Asaas {suffix}",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("10.00"),
            sessions_per_week=1,
            description="Plano temporario para homologacao sandbox do checkout Asaas.",
            public_description="Plano temporario para homologacao segura em sandbox.",
            show_on_website=True,
            active=True,
        )

    def create_public_plan_order(self, suffix):
        plan = self.create_plan(suffix)
        return CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            plan=plan,
            customer_name=f"Cliente Sandbox Asaas {suffix}",
            customer_document=self.fake_cpf_from_suffix(suffix),
            amount=plan.monthly_price,
        )

    def create_patient_payment_order(self, suffix):
        plan = self.create_plan(f"{suffix}-mensalidade")
        patient = Patient.objects.create(
            full_name=f"Paciente Sandbox Mensalidade {suffix}",
            cpf=self.fake_cpf_from_suffix(f"{suffix}2"),
            active=True,
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=timezone.localdate().replace(day=1),
            due_date=timezone.localdate(),
            amount=plan.monthly_price,
            status=Payment.Status.PENDING,
        )
        return CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.PAYMENT,
            patient=patient,
            plan=plan,
            payment=payment,
            customer_name=patient.full_name,
            customer_document=patient.cpf,
            amount=payment.amount,
        )

    def validate_remote_result(self, order, result, label):
        order.refresh_from_db()
        if not result.get("id") or not order.provider_payment_id:
            raise CommandError(f"Sandbox Asaas nao retornou pagamento para {label}.")
        if not order.provider_customer_id:
            raise CommandError(f"Sandbox Asaas nao retornou cliente para {label}.")
        if not order.checkout_url:
            raise CommandError(f"Sandbox Asaas nao retornou URL de pagamento para {label}.")

    def validate_webhook_token(self, order, event_id):
        payload = self.payment_payload(event_id, "PAYMENT_CONFIRMED", order, "PIX", "confirmedDate")
        request = self.build_webhook_request(payload)
        parsed_payload, token_valid = parse_asaas_payload(request)
        if not token_valid or parsed_payload.get("id") != event_id:
            raise CommandError("Validacao local do token de webhook falhou.")

    def validate_webhook_business_flow(self, order, event_id):
        payload = self.payment_payload(event_id, "PAYMENT_RECEIVED", order, "PIX", "paymentDate")
        event, created = record_asaas_checkout_webhook(payload, token_valid=True)
        repeated_event, repeated_created = record_asaas_checkout_webhook(payload, token_valid=True)
        order.refresh_from_db()
        order.payment.refresh_from_db()
        if not created or repeated_created or event.pk != repeated_event.pk:
            raise CommandError("Falha na idempotencia do webhook sandbox simulado.")
        if order.status != CheckoutOrder.Status.PAID or order.payment.status != Payment.Status.PAID:
            raise CommandError("Webhook sandbox simulado nao baixou a mensalidade no financeiro.")

    def build_webhook_request(self, payload):
        return RequestFactory().post(
            "/checkout/webhooks/asaas/",
            data=payload,
            content_type="application/json",
            HTTP_ASAAS_ACCESS_TOKEN=settings.ASAAS_WEBHOOK_TOKEN,
        )

    def payment_payload(self, event_id, event_type, order, billing_type, payment_date_key):
        today = timezone.localdate().isoformat()
        return {
            "id": event_id,
            "event": event_type,
            "payment": {
                "id": order.provider_payment_id,
                "externalReference": order.external_reference,
                "value": str(order.amount),
                "billingType": billing_type,
                payment_date_key: today,
            },
        }

    def fake_cpf_from_suffix(self, suffix):
        numbers = "".join(str(ord(char) % 10) for char in suffix)
        base = (numbers + "123456789")[:9]
        digits = [int(value) for value in base]
        first = self.cpf_digit(digits, range(10, 1, -1))
        second = self.cpf_digit(digits + [first], range(11, 1, -1))
        return "".join(str(value) for value in digits + [first, second])

    def cpf_digit(self, values, weights):
        total = sum(value * weight for value, weight in zip(values, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder
