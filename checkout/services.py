from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import LGPD_CONSENT_VERSION
from accounts.onboarding import ensure_patient_user
from billing.models import Membership, Payment
from checkout.models import CheckoutOrder, CheckoutPaymentEvent
from core.integrations.credentials import first_configured_value
from core.integrations.http import IntegrationError, post_json
from core.models import ClinicSettings
from patients.models import Patient
from scheduling.models import ServicePackage


PAID_EVENTS = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}
FAILED_EVENTS = {"PAYMENT_OVERDUE", "PAYMENT_DELETED", "PAYMENT_REFUNDED", "PAYMENT_CHARGEBACK_REQUESTED"}


def parse_asaas_payload(request):
    configured_token = first_configured_value(settings.ASAAS_WEBHOOK_TOKEN)
    received_token = request.headers.get("asaas-access-token") or request.META.get("HTTP_ASAAS_ACCESS_TOKEN", "")
    token_valid = bool(configured_token and received_token and received_token == configured_token)
    if not configured_token and not settings.DEBUG:
        raise IntegrationError("Configure ASAAS_WEBHOOK_TOKEN antes de receber webhooks em producao.")
    if configured_token and not token_valid:
        raise IntegrationError("Token do webhook Asaas invalido.")
    try:
        import json

        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError as exc:
        raise IntegrationError("Payload de webhook Asaas invalido.") from exc
    return payload, token_valid


class AsaasCheckoutProvider:
    code = CheckoutOrder.Provider.ASAAS

    @property
    def base_url(self):
        return settings.ASAAS_BASE_URL.rstrip("/")

    @property
    def headers(self):
        api_key = first_configured_value(settings.ASAAS_API_KEY)
        if not api_key:
            raise IntegrationError("Configure ASAAS_API_KEY no .env.")
        return {"access_token": api_key}

    def create_customer(self, order):
        if settings.ASAAS_DRY_RUN:
            return {"id": f"cus_checkout_dry_{order.pk}", "dry_run": True}
        payload = {
            "name": order.customer_name,
            "email": order.customer_email or None,
            "mobilePhone": order.customer_phone or None,
            "cpfCnpj": order.customer_document or None,
            "externalReference": f"checkout-customer-{order.external_reference}",
        }
        payload = {key: value for key, value in payload.items() if value}
        return post_json(f"{self.base_url}/customers", payload, headers=self.headers, timeout=settings.ASAAS_TIMEOUT)

    def create_payment(self, order):
        if not order.provider_customer_id:
            customer = self.create_customer(order)
            order.provider_customer_id = customer.get("id", "")
        description = checkout_description(order)
        if settings.ASAAS_DRY_RUN:
            return {
                "id": f"pay_checkout_dry_{order.pk}",
                "customer": order.provider_customer_id,
                "invoiceUrl": f"{settings.SYSTEM_BASE_URL.rstrip('/')}/checkout/pedido/{order.external_reference}/",
                "externalReference": order.external_reference,
                "dry_run": True,
            }
        payload = {
            "customer": order.provider_customer_id,
            "billingType": "UNDEFINED",
            "value": float(order.amount),
            "dueDate": timezone.localdate().isoformat(),
            "description": description,
            "externalReference": order.external_reference,
        }
        return post_json(f"{self.base_url}/payments", payload, headers=self.headers, timeout=settings.ASAAS_TIMEOUT)


def get_checkout_provider():
    provider = settings.CHECKOUT_PAYMENT_PROVIDER.lower()
    if provider == CheckoutOrder.Provider.ASAAS:
        return AsaasCheckoutProvider()
    raise IntegrationError(f"Provider de checkout nao suportado: {provider}")


def checkout_description(order):
    if order.kind == CheckoutOrder.Kind.PAYMENT and order.payment_id:
        return f"Mensalidade Lume - {order.payment.reference_month:%m/%Y}"
    if order.plan_id:
        return f"Plano Lume - {order.plan.name}"
    return "Checkout Lume"


def start_checkout_order(order):
    provider = get_checkout_provider()
    result = provider.create_payment(order)
    order.provider = provider.code
    order.provider_payment_id = result.get("id", order.provider_payment_id)
    order.provider_customer_id = result.get("customer", order.provider_customer_id)
    order.checkout_url = result.get("invoiceUrl") or result.get("bankSlipUrl") or result.get("checkoutUrl") or ""
    order.status = CheckoutOrder.Status.PENDING
    order.save(
        update_fields=[
            "provider",
            "provider_payment_id",
            "provider_customer_id",
            "checkout_url",
            "status",
            "updated_at",
        ]
    )
    return result


def decimal_from_payload(value, fallback):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def find_order_from_asaas_payload(payload):
    payment_payload = payload.get("payment") or {}
    provider_payment_id = payment_payload.get("id", "")
    external_reference = payment_payload.get("externalReference", "")
    queryset = CheckoutOrder.objects.all()
    if provider_payment_id:
        found = queryset.filter(provider_payment_id=provider_payment_id).first()
        if found:
            return found
    if external_reference:
        return queryset.filter(external_reference=external_reference).first()
    return None


def record_asaas_checkout_webhook(payload, token_valid):
    event_type = payload.get("event", "")
    payment_payload = payload.get("payment") or {}
    provider_payment_id = payment_payload.get("id", "")
    external_reference = payment_payload.get("externalReference", "")
    event_id = payload.get("id") or f"asaas-checkout:{event_type}:{provider_payment_id or external_reference}"
    order = find_order_from_asaas_payload(payload)
    event, created = CheckoutPaymentEvent.objects.get_or_create(
        provider=CheckoutOrder.Provider.ASAAS,
        event_id=event_id,
        defaults={
            "event_type": event_type,
            "order": order,
            "provider_payment_id": provider_payment_id,
            "external_reference": external_reference,
            "access_token_valid": token_valid,
            "raw_payload": payload,
        },
    )
    if not created:
        return event, False
    processed = apply_checkout_event(event)
    event.processed_at = timezone.now() if processed else None
    event.save(update_fields=["processed_at", "updated_at"])
    return event, True


def apply_checkout_event(event):
    if not event.order_id:
        return False
    if event.event_type in PAID_EVENTS:
        process_paid_order(event.order_id, event.raw_payload)
        return True
    if event.event_type in FAILED_EVENTS:
        CheckoutOrder.objects.filter(pk=event.order_id, status=CheckoutOrder.Status.PENDING).update(
            status=CheckoutOrder.Status.FAILED,
            raw_payload=event.raw_payload,
            updated_at=timezone.now(),
        )
        return True
    return False


@transaction.atomic
def process_paid_order(order_id, payload):
    order = CheckoutOrder.objects.select_for_update().select_related("payment", "plan", "patient").get(pk=order_id)
    if order.processed_at:
        return order
    payment_payload = payload.get("payment") or {}
    order.mark_paid(payload=payload)
    if order.kind == CheckoutOrder.Kind.PAYMENT:
        finalize_existing_payment_order(order, payment_payload)
    elif order.kind == CheckoutOrder.Kind.SERVICE_PLAN:
        finalize_service_plan_order(order, payment_payload)
    order.processed_at = timezone.now()
    order.save(
        update_fields=[
            "status",
            "paid_at",
            "processed_at",
            "created_patient",
            "created_membership",
            "created_package",
            "raw_payload",
            "updated_at",
        ]
    )
    return order


def finalize_existing_payment_order(order, payment_payload):
    if not order.payment_id:
        raise IntegrationError("Pedido de mensalidade sem pagamento vinculado.")
    paid_on = parse_asaas_date(
        payment_payload.get("clientPaymentDate")
        or payment_payload.get("confirmedDate")
        or payment_payload.get("paymentDate")
    )
    order.payment.status = Payment.Status.PAID
    order.payment.method = payment_method_from_payload(payment_payload)
    order.payment.paid_at = paid_on
    order.payment.notes = append_note(order.payment.notes, f"Pago pelo checkout {order.external_reference}.")
    order.payment.save(update_fields=["status", "method", "paid_at", "notes", "updated_at"])


def finalize_service_plan_order(order, payment_payload):
    patient = order.patient or find_existing_patient(order) or create_patient_from_order(order)
    order.created_patient = patient
    ensure_patient_user(patient, send_notifications=True)
    mark_patient_lgpd_consent(patient)
    membership = ensure_membership_for_order(order, patient)
    order.created_membership = membership
    payment = ensure_paid_membership_payment(order, membership, payment_payload)
    package = ensure_initial_service_package(order, membership)
    order.payment = payment
    order.created_package = package
    order.save(update_fields=["payment", "updated_at"])


def find_existing_patient(order):
    if order.customer_document:
        patient = Patient.objects.filter(cpf=order.customer_document).first()
        if patient:
            return patient
    if order.customer_email:
        patient = Patient.objects.filter(email__iexact=order.customer_email).first()
        if patient:
            return patient
    if order.customer_phone:
        return Patient.objects.filter(phone__contains=order.customer_phone[-8:]).first()
    return None


def create_patient_from_order(order):
    patient = Patient(
        full_name=order.customer_name,
        cpf=order.customer_document or None,
        birth_date=order.customer_birth_date,
        phone=order.customer_phone,
        email=order.customer_email,
        clinical_notes="Cadastro criado automaticamente apos pagamento confirmado no checkout publico.",
        active=True,
    )
    patient.full_clean()
    patient.save()
    return patient


def ensure_membership_for_order(order, patient):
    active_membership = Membership.objects.filter(patient=patient, status=Membership.Status.ACTIVE).first()
    if active_membership:
        if active_membership.plan_id != order.plan_id:
            active_membership.status = Membership.Status.CANCELED
            active_membership.notes = append_note(
                active_membership.notes,
                f"Cancelada automaticamente pela adesao ao plano {order.plan.name} no checkout.",
            )
            active_membership.save(update_fields=["status", "notes", "updated_at"])
        else:
            return active_membership
    settings_object = ClinicSettings.load()
    return Membership.objects.create(
        patient=patient,
        plan=order.plan,
        due_day=settings_object.default_membership_due_day,
        status=Membership.Status.ACTIVE,
        notes=f"Criada automaticamente pelo checkout {order.external_reference}.",
    )


def ensure_paid_membership_payment(order, membership, payment_payload):
    paid_on = parse_asaas_date(
        payment_payload.get("clientPaymentDate")
        or payment_payload.get("confirmedDate")
        or payment_payload.get("paymentDate")
    )
    reference_month = paid_on.replace(day=1)
    payment, _ = Payment.objects.get_or_create(
        membership=membership,
        reference_month=reference_month,
        defaults={
            "due_date": paid_on,
            "amount": decimal_from_payload(payment_payload.get("value"), order.amount),
        },
    )
    payment.status = Payment.Status.PAID
    payment.method = payment_method_from_payload(payment_payload)
    payment.paid_at = paid_on
    payment.amount = decimal_from_payload(payment_payload.get("value"), order.amount)
    payment.notes = append_note(payment.notes, f"Pagamento confirmado pelo checkout {order.external_reference}.")
    payment.save(update_fields=["status", "method", "paid_at", "amount", "notes", "updated_at"])
    return payment


def ensure_initial_service_package(order, membership):
    if not order.plan_id:
        return None
    total_sessions = max(order.plan.sessions_per_week * 4, 1)
    existing = ServicePackage.objects.filter(
        membership=membership,
        status=ServicePackage.Status.ACTIVE,
        notes__contains=order.external_reference,
    ).first()
    if existing:
        return existing
    return ServicePackage.objects.create(
        membership=membership,
        total_sessions=total_sessions,
        used_sessions=0,
        starts_on=timezone.localdate(),
        status=ServicePackage.Status.ACTIVE,
        notes=f"Pacote inicial criado automaticamente pelo checkout {order.external_reference}.",
    )


def parse_asaas_date(value):
    if not value:
        return timezone.localdate()
    try:
        from datetime import datetime

        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return timezone.localdate()


def payment_method_from_payload(payment_payload):
    billing_type = (payment_payload.get("billingType") or "").upper()
    if billing_type == "PIX":
        return Payment.Method.PIX
    if billing_type in {"CREDIT_CARD", "DEBIT_CARD"}:
        return Payment.Method.CARD
    if billing_type in {"BOLETO", "UNDEFINED"}:
        return Payment.Method.TRANSFER
    return Payment.Method.MANUAL


def append_note(existing, addition):
    existing = (existing or "").strip()
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}\n{addition}"


def mark_patient_lgpd_consent(patient):
    profile = getattr(patient, "user_profile", None)
    if not profile:
        return
    now = timezone.now()
    profile.terms_accepted_at = profile.terms_accepted_at or now
    profile.privacy_policy_accepted_at = profile.privacy_policy_accepted_at or now
    profile.sensitive_data_consent_at = profile.sensitive_data_consent_at or now
    profile.lgpd_consent_version = profile.lgpd_consent_version or LGPD_CONSENT_VERSION
    profile.save(
        update_fields=[
            "terms_accepted_at",
            "privacy_policy_accepted_at",
            "sensitive_data_consent_at",
            "lgpd_consent_version",
            "updated_at",
        ]
    )
