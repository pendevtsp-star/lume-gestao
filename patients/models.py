from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel


def only_digits(value):
    value = value or ""
    return "".join(character for character in value if character.isdigit())


class Patient(TimeStampedModel):
    full_name = models.CharField("nome completo", max_length=180)
    cpf = models.CharField("CPF", max_length=14, blank=True, null=True, unique=True)
    birth_date = models.DateField("data de nascimento", null=True, blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    emergency_contact = models.CharField("contato de emergencia", max_length=180, blank=True)
    address = models.CharField("endereco", max_length=255, blank=True)
    clinical_notes = models.TextField("observacoes clinicas", blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "paciente"
        verbose_name_plural = "pacientes"

    def __str__(self):
        return self.full_name

    def clean(self):
        super().clean()
        digits = only_digits(self.cpf)
        if not digits:
            self.cpf = None
            return
        if len(digits) != 11:
            raise ValidationError({"cpf": "Informe um CPF com 11 digitos."})
        self.cpf = digits

# Create your models here.
