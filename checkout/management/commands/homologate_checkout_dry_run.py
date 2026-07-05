from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from billing.models import Membership, Payment, ServicePlan
from checkout.models import CheckoutOrder
from checkout.services import record_asaas_checkout_webhook, start_checkout_order
from patients.models import Patient


class Command(BaseCommand):
    help = "Executa uma homologacao local do checkout Asaas em dry-run, sem cobranca real."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-data",
            action="store_true",
            help="Mantem os dados de homologacao no banco. Por padrao tudo e descartado ao final.",
        )

    def handle(self, *args, **options):
        self.validate_safe_settings()
        keep_data = options["keep_data"]

        with transaction.atomic():
            suffix = uuid4().hex[:10]
            plan_result = self.run_public_plan_flow(suffix)
            payment_result = self.run_patient_payment_flow(suffix)

            self.stdout.write(self.style.SUCCESS("Homologacao Checkout Asaas dry-run concluida."))
            self.stdout.write(f"Modo: ASAAS_DRY_RUN=True | Provider: {settings.CHECKOUT_PAYMENT_PROVIDER}")
            self.stdout.write(
                "Fluxo 1: compra publica de plano confirmada por webhook "
                f"({plan_result['order_reference']})."
            )
            self.stdout.write(
                "Fluxo 2: mensalidade pendente paga por webhook "
                f"({payment_result['order_reference']})."
            )
            self.stdout.write("Idempotencia: ok nos dois webhooks simulados.")

            if keep_data:
                self.stdout.write(self.style.WARNING("Dados temporarios mantidos por --keep-data."))
            else:
                transaction.set_rollback(True)
                self.stdout.write("Dados temporarios descartados automaticamente.")

    def validate_safe_settings(self):
        if settings.CHECKOUT_PAYMENT_PROVIDER != CheckoutOrder.Provider.ASAAS:
            raise CommandError("Esta homologacao esta preparada apenas para CHECKOUT_PAYMENT_PROVIDER=asaas.")
        if not settings.ASAAS_DRY_RUN:
            raise CommandError("Homologacao bloqueada: defina ASAAS_DRY_RUN=True para evitar cobranca real.")
        required_flags = {
            "CHECKOUT_ENABLED": settings.CHECKOUT_ENABLED,
            "CHECKOUT_PUBLIC_ENABLED": settings.CHECKOUT_PUBLIC_ENABLED,
            "CHECKOUT_PATIENT_ENABLED": settings.CHECKOUT_PATIENT_ENABLED,
            "CHECKOUT_WEBHOOK_ENABLED": settings.CHECKOUT_WEBHOOK_ENABLED,
        }
        disabled = [name for name, enabled in required_flags.items() if not enabled]
        if disabled:
            raise CommandError("Ative as flags de checkout para homologacao: " + ", ".join(disabled))

    def create_plan(self, suffix):
        return ServicePlan.objects.create(
            name=f"Homologacao Checkout Asaas {suffix}",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("120.00"),
            sessions_per_week=2,
            description="Plano temporario para homologacao dry-run do checkout Asaas.",
            public_description="Plano temporario para homologacao segura.",
            show_on_website=True,
            active=True,
        )

    def run_public_plan_flow(self, suffix):
        plan = self.create_plan(suffix)
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.SERVICE_PLAN,
            plan=plan,
            customer_name=f"Cliente Homologacao Asaas {suffix}",
            amount=plan.monthly_price,
        )
        start_checkout_order(order)
        payload = self.payment_payload(
            event_id=f"evt_homolog_plan_{suffix}",
            event_type="PAYMENT_CONFIRMED",
            order=order,
            billing_type="PIX",
            payment_date_key="confirmedDate",
        )

        event, created = record_asaas_checkout_webhook(payload, token_valid=True)
        repeated_event, repeated_created = record_asaas_checkout_webhook(payload, token_valid=True)
        order.refresh_from_db()

        if not created or repeated_created or event.pk != repeated_event.pk:
            raise CommandError("Falha na idempotencia do webhook de compra publica.")
        if order.status != CheckoutOrder.Status.PAID:
            raise CommandError("Compra publica nao foi marcada como paga.")
        if not order.created_patient_id or not order.created_membership_id or not order.created_package_id:
            raise CommandError("Compra publica nao criou paciente, mensalidade e pacote inicial.")
        if not order.payment_id or order.payment.status != Payment.Status.PAID:
            raise CommandError("Compra publica nao gerou pagamento quitado.")

        return {"order_reference": order.external_reference}

    def run_patient_payment_flow(self, suffix):
        plan = self.create_plan(f"{suffix}-mensalidade")
        patient = Patient.objects.create(full_name=f"Paciente Mensalidade Homologacao {suffix}", active=True)
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=timezone.localdate().replace(day=1),
            due_date=timezone.localdate(),
            amount=Decimal("120.00"),
            status=Payment.Status.PENDING,
        )
        order = CheckoutOrder.objects.create(
            kind=CheckoutOrder.Kind.PAYMENT,
            patient=patient,
            plan=plan,
            payment=payment,
            customer_name=patient.full_name,
            amount=payment.amount,
        )
        start_checkout_order(order)
        payload = self.payment_payload(
            event_id=f"evt_homolog_payment_{suffix}",
            event_type="PAYMENT_RECEIVED",
            order=order,
            billing_type="CREDIT_CARD",
            payment_date_key="paymentDate",
        )

        event, created = record_asaas_checkout_webhook(payload, token_valid=True)
        repeated_event, repeated_created = record_asaas_checkout_webhook(payload, token_valid=True)
        order.refresh_from_db()
        payment.refresh_from_db()

        if not created or repeated_created or event.pk != repeated_event.pk:
            raise CommandError("Falha na idempotencia do webhook de mensalidade.")
        if order.status != CheckoutOrder.Status.PAID:
            raise CommandError("Pedido de mensalidade nao foi marcado como pago.")
        if payment.status != Payment.Status.PAID or payment.method != Payment.Method.CARD:
            raise CommandError("Mensalidade nao foi baixada como paga no financeiro.")

        return {"order_reference": order.external_reference}

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
