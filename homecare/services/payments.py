from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone

from core.integrations.credentials import first_configured_value
from core.integrations.http import IntegrationError, post_json
from billing.models import Charge
from homecare.models import HomecarePaymentEvent, HomecareSubscription


class PaymentProvider:
    code = ""

    def create_customer(self, subscription):
        raise NotImplementedError

    def create_subscription(self, subscription):
        raise NotImplementedError

    def parse_webhook(self, request):
        raise NotImplementedError


class AsaasProvider(PaymentProvider):
    code = HomecareSubscription.Provider.ASAAS

    @property
    def base_url(self):
        return settings.ASAAS_BASE_URL.rstrip("/")

    @property
    def headers(self):
        api_key = first_configured_value(settings.ASAAS_API_KEY)
        if not api_key:
            raise IntegrationError("Configure ASAAS_API_KEY no .env.")
        return {"access_token": api_key}

    def create_customer(self, subscription):
        patient = subscription.patient
        if settings.ASAAS_DRY_RUN:
            return {"id": f"cus_dry_{patient.pk}", "dry_run": True}
        payload = {
            "name": patient.full_name,
            "email": patient.email or None,
            "mobilePhone": patient.phone or None,
            "cpfCnpj": patient.cpf or None,
            "externalReference": f"patient-{patient.pk}",
        }
        payload = {key: value for key, value in payload.items() if value}
        return post_json(f"{self.base_url}/customers", payload, headers=self.headers, timeout=settings.ASAAS_TIMEOUT)

    def create_subscription(self, subscription):
        if not subscription.provider_customer_id:
            customer = self.create_customer(subscription)
            subscription.provider_customer_id = customer.get("id", "")
        if settings.ASAAS_DRY_RUN:
            reference = subscription.external_reference
            return {
                "id": f"sub_dry_{subscription.pk}",
                "customer": subscription.provider_customer_id,
                "invoiceUrl": f"{settings.SYSTEM_BASE_URL.rstrip('/')}/pilates-em-casa/assinatura/{reference}/",
                "externalReference": reference,
                "dry_run": True,
            }
        due_date = timezone.localdate() + timedelta(days=1)
        payload = {
            "customer": subscription.provider_customer_id,
            "billingType": "UNDEFINED",
            "value": float(subscription.plan.monthly_price),
            "nextDueDate": due_date.isoformat(),
            "cycle": "MONTHLY",
            "description": subscription.plan.name,
            "externalReference": subscription.external_reference,
        }
        return post_json(f"{self.base_url}/subscriptions", payload, headers=self.headers, timeout=settings.ASAAS_TIMEOUT)

    def parse_webhook(self, request):
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


def get_payment_provider():
    provider = settings.HOMECARE_PAYMENT_PROVIDER.lower()
    if provider == HomecareSubscription.Provider.ASAAS:
        return AsaasProvider()
    raise IntegrationError(f"Provider de pagamento nao suportado: {provider}")


def start_checkout_subscription(subscription):
    provider = get_payment_provider()
    result = provider.create_subscription(subscription)
    subscription.provider = provider.code
    subscription.provider_subscription_id = result.get("id", subscription.provider_subscription_id)
    subscription.provider_customer_id = result.get("customer", subscription.provider_customer_id)
    subscription.checkout_url = result.get("invoiceUrl") or result.get("bankSlipUrl") or result.get("checkoutUrl") or ""
    subscription.source = HomecareSubscription.Source.CHECKOUT
    subscription.save(
        update_fields=[
            "provider",
            "provider_subscription_id",
            "provider_customer_id",
            "checkout_url",
            "source",
            "updated_at",
        ]
    )
    return result


def find_subscription_from_asaas_payload(payload):
    payment = payload.get("payment") or {}
    subscription_payload = payload.get("subscription") or {}
    provider_subscription_id = (
        payment.get("subscription")
        or subscription_payload.get("id")
        or payload.get("subscription")
        or ""
    )
    external_reference = payment.get("externalReference") or subscription_payload.get("externalReference") or ""
    queryset = HomecareSubscription.objects.all()
    if provider_subscription_id:
        found = queryset.filter(provider_subscription_id=provider_subscription_id).first()
        if found:
            return found
    if external_reference:
        return queryset.filter(external_reference=external_reference).first()
    return None


def apply_asaas_event_to_subscription(event):
    subscription = event.subscription
    if not subscription:
        return False
    event_type = event.event_type
    now = timezone.now()
    if event_type in {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED", "SUBSCRIPTION_CREATED", "SUBSCRIPTION_UPDATED"}:
        subscription.status = HomecareSubscription.Status.ACTIVE
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=31)
    elif event_type in {"PAYMENT_OVERDUE", "PAYMENT_RESTORED"}:
        subscription.status = HomecareSubscription.Status.PAST_DUE
    elif event_type in {"SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED", "PAYMENT_DELETED"}:
        subscription.status = HomecareSubscription.Status.CANCELED
        subscription.canceled_at = now
    else:
        return False
    subscription.save(
        update_fields=[
            "status",
            "current_period_start",
            "current_period_end",
            "canceled_at",
            "updated_at",
        ]
    )
    if event_type in {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}:
        sync_subscription_revenue(event)
    return True


def parse_asaas_date(value):
    if not value:
        return timezone.localdate()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return timezone.localdate()


def decimal_from_payload(value, fallback):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def sync_subscription_revenue(event):
    if event.finance_charge_id or not event.subscription_id:
        return event.finance_charge
    if event.provider_payment_id:
        existing_event = (
            HomecarePaymentEvent.objects.select_related("finance_charge")
            .filter(provider=event.provider, provider_payment_id=event.provider_payment_id, finance_charge__isnull=False)
            .exclude(pk=event.pk)
            .first()
        )
        if existing_event and existing_event.finance_charge_id:
            event.finance_charge = existing_event.finance_charge
            event.save(update_fields=["finance_charge", "updated_at"])
            return existing_event.finance_charge

    subscription = event.subscription
    payment_payload = event.raw_payload.get("payment") or {}
    amount = decimal_from_payload(payment_payload.get("value"), subscription.plan.monthly_price)
    received_at = parse_asaas_date(
        payment_payload.get("clientPaymentDate")
        or payment_payload.get("confirmedDate")
        or payment_payload.get("paymentDate")
    )
    due_date = parse_asaas_date(payment_payload.get("dueDate")) if payment_payload.get("dueDate") else received_at
    charge = Charge.objects.create(
        patient=subscription.patient,
        description=f"Fisioterapia em Casa - {subscription.plan.name}",
        due_date=due_date,
        amount=amount,
        status=Charge.Status.RECEIVED,
        received_at=received_at,
        notes=(
            f"Receita sincronizada automaticamente pelo modulo Fisioterapia em Casa.\n"
            f"Provider: {event.provider}\n"
            f"Evento: {event.event_id}\n"
            f"Pagamento: {event.provider_payment_id or '-'}\n"
            f"Assinatura: {event.provider_subscription_id or subscription.external_reference}"
        ),
    )
    event.finance_charge = charge
    event.save(update_fields=["finance_charge", "updated_at"])
    return charge


def record_asaas_webhook(payload, token_valid):
    event_type = payload.get("event", "")
    payment = payload.get("payment") or {}
    subscription_payload = payload.get("subscription") or {}
    provider_payment_id = payment.get("id", "")
    provider_subscription_id = payment.get("subscription") or subscription_payload.get("id") or ""
    external_reference = payment.get("externalReference") or subscription_payload.get("externalReference") or ""
    event_id = payload.get("id") or f"asaas:{event_type}:{provider_payment_id or provider_subscription_id or external_reference}"
    subscription = find_subscription_from_asaas_payload(payload)
    event, created = HomecarePaymentEvent.objects.get_or_create(
        provider=HomecareSubscription.Provider.ASAAS,
        event_id=event_id,
        defaults={
            "event_type": event_type,
            "subscription": subscription,
            "finance_charge": None,
            "patient": subscription.patient if subscription else None,
            "provider_subscription_id": provider_subscription_id,
            "provider_payment_id": provider_payment_id,
            "external_reference": external_reference,
            "access_token_valid": token_valid,
            "raw_payload": payload,
        },
    )
    if not created:
        return event, False
    processed = apply_asaas_event_to_subscription(event)
    event.processed_at = timezone.now() if processed else None
    event.save(update_fields=["processed_at", "updated_at"])
    return event, True
