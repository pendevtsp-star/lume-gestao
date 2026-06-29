from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel


def only_digits(value):
    value = value or ""
    return "".join(character for character in value if character.isdigit())


class Patient(TimeStampedModel):
    full_name = models.CharField("nome completo", max_length=180)
    photo = models.ImageField("foto", upload_to="patients/photos/", blank=True)
    cpf = models.CharField("CPF", max_length=14, blank=True, null=True, unique=True)
    birth_date = models.DateField("data de nascimento", null=True, blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    emergency_contact = models.CharField("contato de emergencia", max_length=180, blank=True)
    address = models.CharField("endereco", max_length=255, blank=True)
    clinical_notes = models.TextField("observacoes clinicas", blank=True)
    active = models.BooleanField("ativo", default=True)
    deletion_requested_at = models.DateTimeField("exclusao solicitada em", null=True, blank=True)

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


class ProfessionalPatientAssignment(TimeStampedModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="professional_assignments")
    professional = models.ForeignKey("team.Professional", on_delete=models.PROTECT, related_name="patient_assignments")
    active = models.BooleanField("ativo", default=True)
    notes = models.CharField("observacoes", max_length=255, blank=True)

    class Meta:
        ordering = ["patient__full_name", "professional__full_name"]
        constraints = [
            models.UniqueConstraint(fields=["patient", "professional"], name="unique_patient_professional_assignment")
        ]
        verbose_name = "vinculo paciente-profissional"
        verbose_name_plural = "vinculos paciente-profissional"

    def __str__(self):
        return f"{self.patient} -> {self.professional}"


class ProfessionalNote(TimeStampedModel):
    class RecordType(models.TextChoices):
        CLINICAL_EVALUATION = "clinical_evaluation", "Avaliacao clinica"
        DIAGNOSIS = "diagnosis", "Diagnostico"
        PHYSICAL_EXAM = "physical_exam", "Exame fisico clinico"
        DAILY_EVOLUTION = "daily_evolution", "Evolucao diaria"
        INITIAL = "initial", "Avaliacao inicial"
        EVOLUTION = "evolution", "Evolucao"
        REASSESSMENT = "reassessment", "Reavaliacao"
        DISCHARGE = "discharge", "Alta"

    class SessionFocus(models.TextChoices):
        PILATES = "pilates", "Pilates"
        PHYSIOTHERAPY = "physiotherapy", "Fisioterapia"
        STRENGTH = "strength", "Fortalecimento"
        MOBILITY = "mobility", "Mobilidade"
        PAIN = "pain", "Controle de dor"
        POSTURE = "posture", "Postura"

    class ClinicalStatus(models.TextChoices):
        IMPROVED = "improved", "Melhorou"
        STABLE = "stable", "Estavel"
        WORSENED = "worsened", "Piorou"
        REASSESS = "reassess", "Reavaliar"

    class Conduct(models.TextChoices):
        KEEP = "keep", "Manter plano"
        PROGRESS = "progress", "Progredir exercicios"
        REDUCE = "reduce", "Reduzir carga"
        REASSESS = "reassess", "Reavaliar conduta"

    EXERCISE_GROUP_CHOICES = [
        ("solo_livre", "Solo livre"),
        ("solo_rolo", "Solo rolo"),
        ("solo_bola", "Solo bola"),
        ("theraband", "Theraband"),
        ("magic_circle", "Magic circle"),
        ("jumpboard", "Jumpboard"),
        ("reformer_membros_superiores", "Reformer MMSS"),
        ("reformer_membros_inferiores", "Reformer MMII"),
        ("reformer_alongamento", "Reformer alongamento"),
        ("reformer_abdominais", "Reformer abdominais"),
        ("reformer_costas", "Reformer costas"),
        ("cadillac", "Cadillac"),
        ("chair", "Chair"),
        ("barrel", "Barrel"),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="professional_notes")
    professional = models.ForeignKey("team.Professional", on_delete=models.PROTECT, related_name="patient_notes")
    title = models.CharField("titulo", max_length=140)
    record_type = models.CharField(
        "tipo de registro",
        max_length=30,
        choices=RecordType.choices,
        default=RecordType.DAILY_EVOLUTION,
    )
    session_focus = models.CharField(
        "foco do atendimento",
        max_length=30,
        choices=SessionFocus.choices,
        blank=True,
    )
    objective = models.CharField("objetivo", max_length=220, blank=True)
    exercise_groups = models.JSONField("selecoes de exercicios", default=list, blank=True)
    pain_level = models.PositiveSmallIntegerField("nivel de dor", null=True, blank=True)
    clinical_status = models.CharField(
        "evolucao clinica",
        max_length=20,
        choices=ClinicalStatus.choices,
        blank=True,
    )
    conduct = models.CharField("conduta", max_length=20, choices=Conduct.choices, blank=True)
    structured_data = models.JSONField("dados estruturados", default=dict, blank=True)
    body = models.TextField("observacoes", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "anotacao profissional"
        verbose_name_plural = "anotacoes profissionais"

    def __str__(self):
        return f"{self.patient} - {self.title}"

    @property
    def exercise_groups_display(self):
        labels = dict(self.EXERCISE_GROUP_CHOICES)
        return ", ".join(labels.get(value, value) for value in self.exercise_groups or []) or "-"

    def clean(self):
        super().clean()
        if self.pain_level is not None and not 0 <= self.pain_level <= 10:
            raise ValidationError({"pain_level": "Informe um nivel de dor entre 0 e 10."})

    @property
    def structured_summary(self):
        if not self.structured_data:
            return "-"
        labels = []
        for value in self.structured_data.values():
            if isinstance(value, list):
                labels.extend(str(item) for item in value if item)
            elif value:
                labels.append(str(value))
            if len(labels) >= 3:
                break
        return "; ".join(labels[:3]) or "-"
