from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class FiscalSettings(TimeStampedModel):
    class Provider(models.TextChoices):
        MANUAL = "manual", "Prefeitura/manual"
        NACIONAL = "nacional", "NFS-e Nacional"
        FOCUS_NFE = "focus_nfe", "Focus NFe"
        PLUGNOTAS = "plugnotas", "PlugNotas"
        NFE_IO = "nfe_io", "NFE.io"
        TECNOSPEED = "tecnospeed", "TecnoSpeed"

    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Teste"
        PRODUCTION = "production", "Producao"

    provider = models.CharField("provedor", max_length=30, choices=Provider.choices, default=Provider.MANUAL)
    environment = models.CharField("ambiente", max_length=20, choices=Environment.choices, default=Environment.SANDBOX)
    municipality = models.CharField("municipio de emissao", max_length=120, blank=True)
    cnpj = models.CharField("CNPJ da clinica", max_length=18, blank=True)
    municipal_registration = models.CharField("inscricao municipal", max_length=40, blank=True)
    tax_regime = models.CharField("regime tributario", max_length=80, blank=True)
    default_service_code = models.CharField("codigo de servico padrao", max_length=30, blank=True)
    default_iss_rate = models.DecimalField("ISS padrao (%)", max_digits=5, decimal_places=2, default=Decimal("0.00"))
    api_key = models.CharField("token/chave da integracao", max_length=255, blank=True)
    nfse_enabled = models.BooleanField("habilitar emissao de NFS-e", default=False)
    last_status = models.CharField("ultimo status", max_length=180, blank=True)
    last_error = models.TextField("ultimo erro", blank=True)

    class Meta:
        verbose_name = "configuracao fiscal"
        verbose_name_plural = "configuracoes fiscais"

    def __str__(self):
        return f"Fiscal - {self.get_provider_display()}"

    @classmethod
    def load(cls):
        settings_object, _ = cls.objects.get_or_create(pk=1)
        return settings_object


class FiscalDocument(TimeStampedModel):
    class DocumentType(models.TextChoices):
        NFSE = "nfse", "NFS-e"
        RECEIPT = "receipt", "Cupom/recibo interno"

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        ISSUED = "issued", "Emitida/registrada"
        SENT = "sent", "Enviada"
        CANCELED = "canceled", "Cancelada"
        FAILED = "failed", "Falhou"

    document_type = models.CharField("tipo", max_length=20, choices=DocumentType.choices, default=DocumentType.NFSE)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.DRAFT)
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiscal_documents",
        verbose_name="paciente",
    )
    payment = models.ForeignKey(
        "billing.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiscal_documents",
        verbose_name="pagamento",
    )
    charge = models.ForeignKey(
        "billing.Charge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fiscal_documents",
        verbose_name="cobranca",
    )
    issue_date = models.DateField("data de emissao", default=timezone.localdate)
    description = models.CharField("descricao do servico", max_length=220)
    service_code = models.CharField("codigo de servico", max_length=30, blank=True)
    amount = models.DecimalField(
        "valor do servico",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    iss_rate = models.DecimalField("ISS (%)", max_digits=5, decimal_places=2, default=Decimal("0.00"))
    iss_amount = models.DecimalField("valor ISS", max_digits=10, decimal_places=2, default=Decimal("0.00"), editable=False)
    total_amount = models.DecimalField("valor total", max_digits=10, decimal_places=2, default=Decimal("0.00"), editable=False)
    customer_name = models.CharField("nome do tomador", max_length=180)
    customer_document = models.CharField("CPF/CNPJ do tomador", max_length=18, blank=True)
    customer_email = models.EmailField("e-mail do tomador", blank=True)
    customer_phone = models.CharField("WhatsApp do tomador", max_length=30, blank=True)
    external_id = models.CharField("numero/referencia externa", max_length=80, blank=True)
    verification_code = models.CharField("codigo de verificacao", max_length=80, blank=True)
    provider_payload = models.JSONField("retorno do provedor", default=dict, blank=True)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        verbose_name = "documento fiscal"
        verbose_name_plural = "documentos fiscais"

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.customer_name} - R$ {self.amount}"

    @property
    def is_nfse(self):
        return self.document_type == self.DocumentType.NFSE

    @property
    def can_issue(self):
        return self.status in {self.Status.DRAFT, self.Status.FAILED}

    def save(self, *args, **kwargs):
        amount = self.amount or Decimal("0.00")
        iss_rate = self.iss_rate or Decimal("0.00")
        self.iss_amount = (amount * iss_rate / Decimal("100")).quantize(Decimal("0.01"))
        self.total_amount = amount
        super().save(*args, **kwargs)
