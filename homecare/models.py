from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from core.models import TimeStampedModel


def unique_slug(instance, source_value, slug_field="slug"):
    base_slug = slugify(source_value or "") or uuid4().hex[:10]
    slug = base_slug
    model = instance.__class__
    index = 2
    queryset = model.objects.filter(**{slug_field: slug})
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    while queryset.exists():
        slug = f"{base_slug}-{index}"
        queryset = model.objects.filter(**{slug_field: slug})
        if instance.pk:
            queryset = queryset.exclude(pk=instance.pk)
        index += 1
    return slug


class HomecareCategory(TimeStampedModel):
    name = models.CharField("nome", max_length=120)
    slug = models.SlugField("slug", max_length=140, unique=True, blank=True)
    description = models.TextField("descricao", blank=True)
    display_order = models.PositiveSmallIntegerField("ordem", default=0, blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "categoria de conteudo"
        verbose_name_plural = "categorias de conteudo"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        return super().save(*args, **kwargs)


class HomecarePlan(TimeStampedModel):
    class BillingCycle(models.TextChoices):
        MONTHLY = "monthly", "Mensal"
        QUARTERLY = "quarterly", "Trimestral"
        YEARLY = "yearly", "Anual"

    name = models.CharField("nome", max_length=120)
    slug = models.SlugField("slug", max_length=140, unique=True, blank=True)
    description = models.TextField("descricao", blank=True)
    monthly_price = models.DecimalField("valor", max_digits=10, decimal_places=2)
    billing_cycle = models.CharField("ciclo", max_length=20, choices=BillingCycle.choices, default=BillingCycle.MONTHLY)
    display_order = models.PositiveSmallIntegerField("ordem", default=0, blank=True)
    active = models.BooleanField("ativo", default=True)
    public_checkout_enabled = models.BooleanField("checkout publico ativo", default=True)
    provider_plan_reference = models.CharField("referencia no provedor", max_length=120, blank=True)

    class Meta:
        ordering = ["display_order", "monthly_price", "name"]
        verbose_name = "plano do canal"
        verbose_name_plural = "planos do canal"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.monthly_price is not None and self.monthly_price <= Decimal("0"):
            raise ValidationError({"monthly_price": "O valor do plano deve ser maior que zero."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        return super().save(*args, **kwargs)


class HomecareVideo(TimeStampedModel):
    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Iniciante"
        INTERMEDIATE = "intermediate", "Intermediario"
        ADVANCED = "advanced", "Avancado"

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        QUEUED = "queued", "Na fila"
        UPLOADING = "uploading", "Enviando"
        PROCESSING = "processing", "Processando"
        READY = "ready", "Pronto"
        FAILED = "failed", "Falhou"
        ARCHIVED = "archived", "Arquivado"

    class Provider(models.TextChoices):
        BUNNY = "bunny", "Bunny Stream"
        MANUAL = "manual", "Manual"

    title = models.CharField("titulo", max_length=160)
    slug = models.SlugField("slug", max_length=180, unique=True, blank=True)
    description = models.TextField("descricao", blank=True)
    category = models.ForeignKey(
        HomecareCategory,
        on_delete=models.PROTECT,
        related_name="videos",
        verbose_name="categoria",
    )
    author = models.ForeignKey(
        "team.Professional",
        on_delete=models.PROTECT,
        related_name="homecare_videos",
        verbose_name="autor",
    )
    specialty = models.CharField("area", max_length=30, blank=True)
    difficulty = models.CharField("nivel", max_length=20, choices=Difficulty.choices, default=Difficulty.BEGINNER)
    duration_seconds = models.PositiveIntegerField("duracao em segundos", default=0, blank=True)
    temporary_file = models.FileField("arquivo temporario", upload_to="homecare/uploads/", blank=True)
    thumbnail = models.ImageField("capa", upload_to="homecare/thumbnails/", blank=True)
    provider = models.CharField("provedor", max_length=20, choices=Provider.choices, default=Provider.BUNNY)
    provider_video_id = models.CharField("ID do video no provedor", max_length=160, blank=True, db_index=True)
    provider_library_id = models.CharField("ID da biblioteca", max_length=160, blank=True)
    provider_embed_url = models.URLField("URL de embed", max_length=500, blank=True)
    provider_payload = models.JSONField("payload do provedor", default=dict, blank=True)
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    upload_error = models.TextField("erro de upload", blank=True)
    is_published = models.BooleanField("publicado", default=False)
    published_at = models.DateTimeField("publicado em", null=True, blank=True)
    scheduled_publish_at = models.DateTimeField(
        "lancamento programado",
        null=True,
        blank=True,
        db_index=True,
        help_text="Data e horario em que o video passa a aparecer para assinantes.",
    )

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "video do canal"
        verbose_name_plural = "videos do canal"

    def __str__(self):
        return self.title

    @property
    def duration_label(self):
        if not self.duration_seconds:
            return "-"
        minutes, seconds = divmod(self.duration_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def can_be_watched(self):
        if not self.is_published or self.status != self.Status.READY or not self.provider_video_id:
            return False
        if self.scheduled_publish_at and self.scheduled_publish_at > timezone.now():
            return False
        return True

    @property
    def is_scheduled(self):
        return bool(self.is_published and self.scheduled_publish_at and self.scheduled_publish_at > timezone.now())

    @property
    def publish_state(self):
        if self.is_scheduled:
            return "scheduled"
        if self.is_published:
            return "published"
        return "draft"

    @property
    def publish_state_label(self):
        labels = {
            "scheduled": "Programado",
            "published": "Publicado",
            "draft": "Rascunho",
        }
        return labels[self.publish_state]

    def publish(self):
        self.is_published = True
        if not self.published_at:
            self.published_at = self.scheduled_publish_at or timezone.now()

    def clean(self):
        super().clean()
        if self.is_published and self.status != self.Status.READY and not self.scheduled_publish_at:
            raise ValidationError({"is_published": "Publique apenas videos com status pronto."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        if self.is_published and self.scheduled_publish_at and self.scheduled_publish_at > timezone.now():
            self.published_at = self.scheduled_publish_at
        elif self.is_published and not self.published_at:
            self.published_at = self.scheduled_publish_at or timezone.now()
        return super().save(*args, **kwargs)


class HomecareSubscription(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        TRIALING = "trialing", "Teste"
        ACTIVE = "active", "Ativa"
        PAST_DUE = "past_due", "Em atraso"
        CANCELED = "canceled", "Cancelada"
        EXPIRED = "expired", "Expirada"

    class Source(models.TextChoices):
        MANUAL = "manual", "Liberacao manual"
        CHECKOUT = "checkout", "Checkout"
        IMPORTED = "imported", "Importada"

    class Provider(models.TextChoices):
        ASAAS = "asaas", "Asaas"
        MANUAL = "manual", "Manual"

    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="homecare_subscriptions")
    plan = models.ForeignKey(HomecarePlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    source = models.CharField("origem", max_length=20, choices=Source.choices, default=Source.MANUAL)
    provider = models.CharField("provedor", max_length=20, choices=Provider.choices, default=Provider.MANUAL)
    starts_at = models.DateTimeField("inicio", default=timezone.now)
    current_period_start = models.DateTimeField("inicio do periodo", null=True, blank=True)
    current_period_end = models.DateTimeField("fim do periodo", null=True, blank=True)
    canceled_at = models.DateTimeField("cancelado em", null=True, blank=True)
    provider_customer_id = models.CharField("cliente no provedor", max_length=120, blank=True)
    provider_subscription_id = models.CharField("assinatura no provedor", max_length=120, blank=True, db_index=True)
    provider_payment_id = models.CharField("pagamento no provedor", max_length=120, blank=True)
    external_reference = models.CharField("referencia externa", max_length=80, unique=True, blank=True)
    checkout_url = models.URLField("URL de checkout", max_length=500, blank=True)
    notes = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "assinatura do canal"
        verbose_name_plural = "assinaturas do canal"

    def __str__(self):
        return f"{self.patient} - {self.plan}"

    @property
    def has_access(self):
        if self.status not in {self.Status.ACTIVE, self.Status.TRIALING}:
            return False
        return not self.current_period_end or self.current_period_end >= timezone.now()

    def activate_for_days(self, days=31):
        now = timezone.now()
        self.status = self.Status.ACTIVE
        self.current_period_start = now
        self.current_period_end = now + timedelta(days=days)

    def save(self, *args, **kwargs):
        if not self.external_reference:
            self.external_reference = f"homecare-{uuid4().hex}"
        return super().save(*args, **kwargs)


class HomecarePaymentEvent(TimeStampedModel):
    provider = models.CharField("provedor", max_length=20, default=HomecareSubscription.Provider.ASAAS)
    event_id = models.CharField("ID do evento", max_length=160, unique=True)
    event_type = models.CharField("tipo", max_length=80)
    subscription = models.ForeignKey(
        HomecareSubscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_events",
    )
    finance_charge = models.ForeignKey(
        "billing.Charge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homecare_payment_events",
        verbose_name="receita no financeiro",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homecare_payment_events",
    )
    provider_subscription_id = models.CharField("assinatura no provedor", max_length=120, blank=True)
    provider_payment_id = models.CharField("pagamento no provedor", max_length=120, blank=True)
    external_reference = models.CharField("referencia externa", max_length=80, blank=True)
    access_token_valid = models.BooleanField("token valido", default=False)
    processed_at = models.DateTimeField("processado em", null=True, blank=True)
    raw_payload = models.JSONField("payload", default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "evento de pagamento do canal"
        verbose_name_plural = "eventos de pagamento do canal"

    def __str__(self):
        return f"{self.provider} - {self.event_type}"


class HomecareVideoProgress(TimeStampedModel):
    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE, related_name="homecare_video_progress")
    video = models.ForeignKey(HomecareVideo, on_delete=models.CASCADE, related_name="progress_records")
    watched_seconds = models.PositiveIntegerField("segundos assistidos", default=0)
    completed = models.BooleanField("concluido", default=False)
    last_watched_at = models.DateTimeField("assistido em", default=timezone.now)

    class Meta:
        ordering = ["-last_watched_at"]
        constraints = [models.UniqueConstraint(fields=["patient", "video"], name="unique_homecare_progress")]
        verbose_name = "progresso de video"
        verbose_name_plural = "progressos de video"

    def __str__(self):
        return f"{self.patient} - {self.video}"


class HomecareVideoLike(models.Model):
    video = models.ForeignKey(HomecareVideo, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="homecare_video_likes")
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["video", "user"], name="unique_homecare_video_like_per_user"),
        ]
        ordering = ["-created_at"]
        verbose_name = "curtida de video do Lume em casa"
        verbose_name_plural = "curtidas de videos do Lume em casa"

    def __str__(self):
        return f"{self.user} curtiu video #{self.video_id}"


class HomecareVideoComment(TimeStampedModel):
    video = models.ForeignKey(HomecareVideo, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="homecare_video_comments",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="replies",
        null=True,
        blank=True,
        verbose_name="comentario respondido",
    )
    content = models.TextField("comentario")
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["video", "is_active", "created_at"]),
            models.Index(fields=["parent", "is_active", "created_at"]),
            models.Index(fields=["author", "-created_at"]),
        ]
        verbose_name = "comentario de video do Lume em casa"
        verbose_name_plural = "comentarios de videos do Lume em casa"

    def __str__(self):
        return f"Comentario #{self.pk} no video #{self.video_id}"

    def clean(self):
        super().clean()
        if not self.parent_id:
            return
        if self.parent.parent_id:
            raise ValidationError({"parent": "Responda apenas comentarios principais."})
        if self.video_id and self.parent.video_id and self.parent.video_id != self.video_id:
            raise ValidationError({"parent": "O comentario respondido precisa pertencer ao mesmo video."})

    @property
    def author_profile(self):
        try:
            return self.author.profile
        except (AttributeError, ObjectDoesNotExist):
            return None

    @property
    def author_name(self):
        profile = self.author_profile
        if profile:
            return profile.display_name
        return self.author.get_full_name() or self.author.username

    @property
    def author_avatar_url(self):
        profile = self.author_profile
        return profile.avatar_url if profile else ""

    @property
    def author_initials(self):
        profile = self.author_profile
        if profile:
            return profile.initials
        name = self.author.get_full_name() or self.author.username
        return (name[:1] or "U").upper()


class HomecareUploadJob(TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Na fila"
        RUNNING = "running", "Processando"
        DONE = "done", "Concluido"
        FAILED = "failed", "Falhou"

    video = models.ForeignKey(HomecareVideo, on_delete=models.CASCADE, related_name="upload_jobs")
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveSmallIntegerField("tentativas", default=0)
    started_at = models.DateTimeField("inicio", null=True, blank=True)
    finished_at = models.DateTimeField("fim", null=True, blank=True)
    error_message = models.TextField("erro", blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "fila de upload do canal"
        verbose_name_plural = "fila de uploads do canal"

    def __str__(self):
        return f"{self.video} - {self.get_status_display()}"
