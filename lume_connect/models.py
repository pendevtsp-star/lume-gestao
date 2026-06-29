from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from core.models import TimeStampedModel


ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]


def validate_connect_image_size(image):
    max_mb = getattr(settings, "LUME_CONNECT_MAX_IMAGE_MB", 8)
    max_bytes = max_mb * 1024 * 1024
    if image and image.size > max_bytes:
        raise ValidationError(f"A imagem deve ter no maximo {max_mb} MB.")


class ConnectPost(TimeStampedModel):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connect_posts")
    content = models.TextField("conteudo", blank=True)
    image = models.ImageField(
        "imagem",
        upload_to="lume_connect/posts/",
        blank=True,
        validators=[FileExtensionValidator(ALLOWED_IMAGE_EXTENSIONS), validate_connect_image_size],
    )
    is_pinned = models.BooleanField("fixado", default=False)
    is_announcement = models.BooleanField("comunicado", default=False)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["is_active", "-is_pinned", "-created_at"]),
            models.Index(fields=["author", "-created_at"]),
        ]
        verbose_name = "post do Lume Connect"
        verbose_name_plural = "posts do Lume Connect"

    def __str__(self):
        return f"Post #{self.pk} - {self.author}"

    def clean(self):
        super().clean()
        if not self.content.strip() and not self.image:
            raise ValidationError("Informe um texto ou uma imagem para publicar.")

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


class ConnectLike(models.Model):
    post = models.ForeignKey(ConnectPost, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connect_likes")
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "user"], name="unique_lume_connect_like_per_user"),
        ]
        ordering = ["-created_at"]
        verbose_name = "curtida do Lume Connect"
        verbose_name_plural = "curtidas do Lume Connect"

    def __str__(self):
        return f"{self.user} curtiu post #{self.post_id}"


class ConnectComment(TimeStampedModel):
    post = models.ForeignKey(ConnectPost, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connect_comments")
    content = models.TextField("comentario")
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["post", "is_active", "created_at"]),
            models.Index(fields=["author", "-created_at"]),
        ]
        verbose_name = "comentario do Lume Connect"
        verbose_name_plural = "comentarios do Lume Connect"

    def __str__(self):
        return f"Comentario #{self.pk} em post #{self.post_id}"

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


class ConnectNotification(models.Model):
    class NotificationType(models.TextChoices):
        LIKE = "like", "Curtida"
        COMMENT = "comment", "Comentario"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connect_notifications")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connect_notifications_sent")
    post = models.ForeignKey(ConnectPost, on_delete=models.CASCADE, related_name="notifications")
    comment = models.ForeignKey(
        ConnectComment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    notification_type = models.CharField("tipo", max_length=20, choices=NotificationType.choices)
    is_read = models.BooleanField("lida", default=False)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
        ]
        verbose_name = "notificacao do Lume Connect"
        verbose_name_plural = "notificacoes do Lume Connect"

    def __str__(self):
        return f"{self.get_notification_type_display()} para {self.recipient}"


class ConnectShareLog(models.Model):
    class TargetPlatform(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        WHATSAPP = "whatsapp", "WhatsApp"
        FACEBOOK = "facebook", "Facebook"
        NATIVE = "native", "Compartilhamento nativo"
        DOWNLOAD = "download", "Download da imagem"
        COPY_CAPTION = "copy_caption", "Copia de legenda"
        OTHER = "other", "Outra rede"

    post = models.ForeignKey(ConnectPost, on_delete=models.CASCADE, related_name="share_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connect_share_logs")
    target_platform = models.CharField("destino", max_length=30, choices=TargetPlatform.choices)
    generated_caption = models.TextField("legenda gerada", blank=True)
    final_caption = models.TextField("legenda final", blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["post", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["target_platform", "-created_at"]),
        ]
        verbose_name = "registro de compartilhamento do Lume Connect"
        verbose_name_plural = "registros de compartilhamento do Lume Connect"

    def __str__(self):
        return f"{self.get_target_platform_display()} - post #{self.post_id}"
