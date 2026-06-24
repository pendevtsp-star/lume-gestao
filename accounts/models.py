from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class UserProfile(TimeStampedModel):
    class Role(models.TextChoices):
        PATIENT = "patient", "Paciente"
        PROFESSIONAL = "professional", "Profissional"
        ADMINISTRATION = "administration", "Administracao"
        MANAGEMENT = "management", "Gerencia"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField("perfil", max_length=30, choices=Role.choices, default=Role.ADMINISTRATION)
    patient = models.OneToOneField(
        "patients.Patient",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profile",
    )
    professional = models.OneToOneField(
        "team.Professional",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profile",
    )
    phone = models.CharField("telefone", max_length=30, blank=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfis de usuario"

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def is_management(self):
        return self.role == self.Role.MANAGEMENT

    @property
    def is_administration(self):
        return self.role == self.Role.ADMINISTRATION

    @property
    def is_professional(self):
        return self.role == self.Role.PROFESSIONAL

    @property
    def is_patient(self):
        return self.role == self.Role.PATIENT

    @property
    def can_manage_finance(self):
        return self.role in {self.Role.ADMINISTRATION, self.Role.MANAGEMENT}

    @property
    def can_manage_users(self):
        return self.role == self.Role.MANAGEMENT

# Create your models here.
