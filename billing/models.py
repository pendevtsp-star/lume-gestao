from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimeStampedModel
from patients.models import Patient


class ServicePlan(TimeStampedModel):
    class Category(models.TextChoices):
        PILATES = "pilates", "Pilates"
        PHYSIOTHERAPY = "physiotherapy", "Fisioterapia"
        MASSAGE = "massage", "Massagem"
        REIKI = "reiki", "Reiki"
        COMBO = "combo", "Combo"
        OTHER = "other", "Outro servico"

    class PlanType(models.TextChoices):
        RECURRING = "recurring", "Plano recorrente"
        SINGLE = "single", "Servico avulso"

    name = models.CharField("nome do plano", max_length=120)
    category = models.CharField("categoria", max_length=30, choices=Category.choices)
    plan_type = models.CharField("tipo", max_length=20, choices=PlanType.choices, default=PlanType.RECURRING)
    monthly_price = models.DecimalField("valor do ciclo", max_digits=10, decimal_places=2)
    duration_months = models.PositiveSmallIntegerField("duracao do ciclo em meses", default=1)
    sessions_per_week = models.PositiveSmallIntegerField("sessoes por semana", default=2)
    included_sessions = models.PositiveSmallIntegerField("atendimentos incluidos no ciclo", default=8)
    description = models.TextField("descricao", blank=True)
    public_description = models.TextField("descricao publica", blank=True)
    show_on_website = models.BooleanField("exibir no site", default=False)
    display_order = models.PositiveSmallIntegerField("ordem no site", default=0, blank=True)
    highlight_badge = models.CharField("selo de destaque", max_length=40, blank=True)
    active = models.BooleanField("ativo", default=True)
    deletion_requested_at = models.DateTimeField("exclusao solicitada em", null=True, blank=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "plano"
        verbose_name_plural = "planos"

    def __str__(self):
        return self.name

    @property
    def is_single_service(self):
        return self.plan_type == self.PlanType.SINGLE

    @property
    def default_total_sessions(self):
        if self.is_single_service:
            return 1
        return max(self.included_sessions, 1)

    def default_expires_on(self, starts_on):
        months = max(self.duration_months or 1, 1)
        return add_months(starts_on, months)

    def clean(self):
        super().clean()
        if self.monthly_price is not None and self.monthly_price <= Decimal("0"):
            raise ValidationError({"monthly_price": "O valor do ciclo deve ser maior que zero."})
        if self.duration_months < 1:
            raise ValidationError({"duration_months": "Informe pelo menos 1 mes de validade."})
        if self.included_sessions < 1:
            raise ValidationError({"included_sessions": "Informe pelo menos 1 atendimento incluido."})
        if self.is_single_service:
            self.included_sessions = 1
            self.sessions_per_week = 1
        if not 1 <= self.sessions_per_week <= 7:
            raise ValidationError({"sessions_per_week": "Informe entre 1 e 7 sessoes por semana."})


def add_months(start_date, months):
    year = start_date.year + (start_date.month - 1 + months) // 12
    month = (start_date.month - 1 + months) % 12 + 1
    day = min(start_date.day, days_in_month(year, month))
    return date(year, month, day)


def days_in_month(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


class Membership(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        PAUSED = "paused", "Pausada"
        CANCELED = "canceled", "Cancelada"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="memberships")
    plan = models.ForeignKey(ServicePlan, on_delete=models.PROTECT, related_name="memberships")
    start_date = models.DateField("data de inicio", default=timezone.localdate)
    due_day = models.PositiveSmallIntegerField("dia de vencimento", default=10)
    discount_amount = models.DecimalField(
        "desconto fixo",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["patient__full_name"]
        verbose_name = "mensalidade"
        verbose_name_plural = "mensalidades"
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "plan"],
                condition=Q(status="active"),
                name="one_active_membership_per_patient_plan",
            )
        ]

    def __str__(self):
        return f"{self.patient} - {self.plan}"

    @property
    def monthly_amount(self):
        return max(self.plan.monthly_price - self.discount_amount, Decimal("0.00"))

    def clean(self):
        super().clean()
        if not 1 <= self.due_day <= 28:
            raise ValidationError({"due_day": "Use um vencimento entre os dias 1 e 28."})
        if self.discount_amount < Decimal("0"):
            raise ValidationError({"discount_amount": "O desconto nao pode ser negativo."})
        if self.plan_id and self.discount_amount > self.plan.monthly_price:
            raise ValidationError({"discount_amount": "O desconto nao pode superar o valor do plano."})


class Payment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PAID = "paid", "Pago"
        OVERDUE = "overdue", "Vencido"
        CANCELED = "canceled", "Cancelado"

    class Method(models.TextChoices):
        MANUAL = "manual", "Manual"
        PIX = "pix", "Pix"
        CASH = "cash", "Dinheiro"
        CARD = "card", "Cartao"
        TRANSFER = "transfer", "Transferencia"

    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="payments")
    reference_month = models.DateField("mes de referencia")
    due_date = models.DateField("vencimento")
    amount = models.DecimalField("valor", max_digits=10, decimal_places=2)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.PENDING)
    method = models.CharField("metodo", max_length=20, choices=Method.choices, default=Method.MANUAL)
    paid_at = models.DateField("pago em", null=True, blank=True)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["-due_date", "membership__patient__full_name"]
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "reference_month"],
                name="one_payment_per_membership_month",
            )
        ]

    def __str__(self):
        return f"{self.membership.patient} - {self.reference_month:%m/%Y}"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0"):
            raise ValidationError({"amount": "O valor do pagamento deve ser maior que zero."})
        if self.status == self.Status.PAID and not self.paid_at:
            raise ValidationError({"paid_at": "Informe a data de pagamento."})
        if self.status != self.Status.PAID and self.paid_at:
            raise ValidationError({"paid_at": "Use data de pagamento apenas quando o status for pago."})
        if self.reference_month and self.reference_month.day != 1:
            raise ValidationError({"reference_month": "Use sempre o primeiro dia do mes de referencia."})


class ExpenseCategory(TimeStampedModel):
    class Kind(models.TextChoices):
        FIXED = "fixed", "Fixa"
        VARIABLE = "variable", "Variavel"

    name = models.CharField("nome", max_length=120, unique=True)
    kind = models.CharField("tipo padrao", max_length=20, choices=Kind.choices, default=Kind.VARIABLE)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "categoria de despesa"
        verbose_name_plural = "categorias de despesa"

    def __str__(self):
        return self.name


class Expense(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        PAID = "paid", "Paga"
        CANCELED = "canceled", "Cancelada"

    class Kind(models.TextChoices):
        FIXED = "fixed", "Fixa"
        VARIABLE = "variable", "Variavel"

    description = models.CharField("descricao", max_length=180)
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        null=True,
        related_name="expenses",
        verbose_name="categoria",
    )
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.VARIABLE)
    amount = models.DecimalField("valor", max_digits=10, decimal_places=2)
    due_date = models.DateField("vencimento")
    paid_at = models.DateField("pago em", null=True, blank=True)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.OPEN)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["-due_date"]
        verbose_name = "despesa"
        verbose_name_plural = "despesas"

    def __str__(self):
        return self.description

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0"):
            raise ValidationError({"amount": "O valor deve ser maior que zero."})
        if self.status == self.Status.PAID and not self.paid_at:
            raise ValidationError({"paid_at": "Informe a data de pagamento."})
        if self.status != self.Status.PAID and self.paid_at:
            raise ValidationError({"paid_at": "Use data de pagamento apenas quando a despesa estiver paga."})


class Charge(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        RECEIVED = "received", "Recebida"
        OVERDUE = "overdue", "Vencida"
        CANCELED = "canceled", "Cancelada"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, null=True, blank=True, related_name="charges")
    description = models.CharField("descricao", max_length=180)
    due_date = models.DateField("vencimento")
    amount = models.DecimalField("valor", max_digits=10, decimal_places=2)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.OPEN)
    received_at = models.DateField("recebida em", null=True, blank=True)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["-due_date"]
        verbose_name = "cobranca avulsa"
        verbose_name_plural = "cobrancas avulsas"

    def __str__(self):
        return self.description

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0"):
            raise ValidationError({"amount": "O valor deve ser maior que zero."})
        if self.status == self.Status.RECEIVED and not self.received_at:
            raise ValidationError({"received_at": "Informe a data de recebimento."})
        if self.status != self.Status.RECEIVED and self.received_at:
            raise ValidationError({"received_at": "Use recebimento apenas quando a cobranca estiver recebida."})
