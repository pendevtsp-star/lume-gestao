from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class ClinicSettings(TimeStampedModel):
    membership_due_reminder_days = models.PositiveSmallIntegerField(
        "dias antes do vencimento",
        default=5,
        help_text="Quantidade de dias para destacar mensalidades proximas do vencimento.",
    )

    class Meta:
        verbose_name = "configuracao da clinica"
        verbose_name_plural = "configuracoes da clinica"

    def __str__(self):
        return "Configuracoes da clinica"

    @classmethod
    def load(cls):
        settings_object, _ = cls.objects.get_or_create(pk=1)
        return settings_object


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Criado"
        UPDATED = "updated", "Atualizado"
        DELETED = "deleted", "Excluido"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField("acao", max_length=20, choices=Action.choices)
    app_label = models.CharField("app", max_length=80)
    model_name = models.CharField("modelo", max_length=80)
    object_id = models.CharField("id do objeto", max_length=80, blank=True)
    object_repr = models.CharField("objeto", max_length=255)
    changes = models.JSONField("alteracoes", default=dict, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"

    def __str__(self):
        return f"{self.get_action_display()} {self.model_name} #{self.object_id}"

# Create your models here.
