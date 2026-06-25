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
    photo = models.ImageField("foto", upload_to="users/photos/", blank=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfis de usuario"

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def display_name(self):
        if self.patient_id:
            return self.patient.full_name
        if self.professional_id:
            return self.professional.full_name
        full_name = self.user.get_full_name()
        return full_name or self.user.username

    @property
    def avatar_url(self):
        if self.patient_id and self.patient.photo:
            return self.patient.photo.url
        if self.professional_id and self.professional.photo:
            return self.professional.photo.url
        if self.photo:
            return self.photo.url
        return ""

    @property
    def initials(self):
        parts = [part for part in self.display_name.split() if part]
        if not parts:
            return "U"
        if len(parts) == 1:
            return parts[0][:1].upper()
        return f"{parts[0][:1]}{parts[-1][:1]}".upper()

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
