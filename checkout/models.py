from decimal import Decimal
from uuid import uuid4

from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class CheckoutOrder(TimeStampedModel):
    class Kind(models.TextChoices):
        SERVICE_PLAN = "service_plan", "Compra de plano"
        PAYMENT = "payment", "Pagamento de mensalidade"

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        PENDING = "pending", "Aguardando pagamento"
        PAID = "paid", "Pago"
        FAILED = "failed", "Falhou"
        CANCELED = "canceled", "Cancelado"
        EXPIRED = "expired", "Expirado"

    class Provider(models.TextChoices):
        ASAAS = "asaas", "Asaas"
        MANUAL = "manual", "Manual"

    kind = models.CharField("tipo", max_length=30, choices=Kind.choices)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    provider = models.CharField("provedor", max_length=20, choices=Provider.choices, default=Provider.ASAAS)
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkout_orders",
    )
    plan = models.ForeignKey(
        "billing.ServicePlan",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="checkout_orders",
    )
    payment = models.ForeignKey(
        "billing.Payment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="checkout_orders",
    )
    customer_name = models.CharField("nome", max_length=180)
    customer_document = models.CharField("CPF", max_length=14, blank=True)
    customer_birth_date = models.DateField("data de nascimento", null=True, blank=True)
    customer_email = models.EmailField("e-mail", blank=True)
    customer_phone = models.CharField("telefone", max_length=30, blank=True)
    amount = models.DecimalField("valor", max_digits=10, decimal_places=2, default=Decimal("0.00"))
    external_reference = models.CharField("referencia externa", max_length=80, unique=True, blank=True)
    provider_customer_id = models.CharField("cliente no provedor", max_length=120, blank=True)
    provider_payment_id = models.CharField("pagamento no provedor", max_length=120, blank=True, db_index=True)
    checkout_url = models.URLField("URL de pagamento", max_length=500, blank=True)
    paid_at = models.DateTimeField("pago em", null=True, blank=True)
    processed_at = models.DateTimeField("processado em", null=True, blank=True)
    created_patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_checkout_orders",
    )
    created_membership = models.ForeignKey(
        "billing.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkout_orders",
    )
    created_package = models.ForeignKey(
        "scheduling.ServicePackage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checkout_orders",
    )
    raw_payload = models.JSONField("payload do provedor", default=dict, blank=True)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "pedido de checkout"
        verbose_name_plural = "pedidos de checkout"

    def __str__(self):
        return f"{self.get_kind_display()} - {self.customer_name} - R$ {self.amount}"

    def save(self, *args, **kwargs):
        if not self.external_reference:
            self.external_reference = f"checkout-{uuid4().hex}"
        return super().save(*args, **kwargs)

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    def mark_paid(self, payload=None):
        self.status = self.Status.PAID
        self.paid_at = self.paid_at or timezone.now()
        if payload:
            self.raw_payload = payload


class CheckoutPaymentEvent(TimeStampedModel):
    provider = models.CharField("provedor", max_length=20, default=CheckoutOrder.Provider.ASAAS)
    event_id = models.CharField("ID do evento", max_length=160, unique=True)
    event_type = models.CharField("tipo", max_length=80)
    order = models.ForeignKey(
        CheckoutOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_events",
    )
    provider_payment_id = models.CharField("pagamento no provedor", max_length=120, blank=True)
    external_reference = models.CharField("referencia externa", max_length=80, blank=True)
    access_token_valid = models.BooleanField("token valido", default=False)
    processed_at = models.DateTimeField("processado em", null=True, blank=True)
    raw_payload = models.JSONField("payload", default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "evento de pagamento do checkout"
        verbose_name_plural = "eventos de pagamento do checkout"

    def __str__(self):
        return f"{self.provider} - {self.event_type}"
