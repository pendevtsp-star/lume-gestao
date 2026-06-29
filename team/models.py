from django.db import models

from core.models import TimeStampedModel


class Employee(TimeStampedModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administracao"
        RECEPTION = "reception", "Recepcao"
        FINANCE = "finance", "Financeiro"

    full_name = models.CharField("nome completo", max_length=180)
    photo = models.ImageField("foto", upload_to="employees/photos/", blank=True)
    role = models.CharField("funcao", max_length=30, choices=Role.choices)
    phone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    admission_date = models.DateField("data de admissao", null=True, blank=True)
    active = models.BooleanField("ativo", default=True)
    deletion_requested_at = models.DateTimeField("exclusao solicitada em", null=True, blank=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "funcionario"
        verbose_name_plural = "funcionarios"

    def __str__(self):
        return self.full_name


class Professional(TimeStampedModel):
    class Specialty(models.TextChoices):
        PHYSIOTHERAPY = "physiotherapy", "Fisioterapia"
        PILATES = "pilates", "Pilates"
        MASSAGE = "massage", "Massagem"
        REIKI = "reiki", "Reiki"
        OTHER = "other", "Outro"

    full_name = models.CharField("nome completo", max_length=180)
    photo = models.ImageField("foto", upload_to="professionals/photos/", blank=True)
    specialty = models.CharField("especialidade", max_length=30, choices=Specialty.choices)
    registration_number = models.CharField("registro profissional", max_length=80, blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    bio = models.TextField("observacoes", blank=True)
    active = models.BooleanField("ativo", default=True)
    deletion_requested_at = models.DateTimeField("exclusao solicitada em", null=True, blank=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "profissional"
        verbose_name_plural = "profissionais"

    def __str__(self):
        return self.full_name

# Create your models here.
