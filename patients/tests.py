from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from patients.models import Patient
from patients.models import ProfessionalNote
from patients.models import ProfessionalPatientAssignment
from team.models import Professional


class PatientModelTests(TestCase):
    def test_cpf_is_normalized_when_valid(self):
        patient = Patient(full_name="Ana Teste", cpf="123.456.789-01")

        patient.full_clean()

        self.assertEqual(patient.cpf, "12345678901")

    def test_cpf_rejects_invalid_length(self):
        patient = Patient(full_name="Ana Teste", cpf="123")

        with self.assertRaises(ValidationError):
            patient.full_clean()

    def test_blank_cpf_is_stored_as_null(self):
        patient = Patient(full_name="Ana Teste", cpf="")

        patient.full_clean()

        self.assertIsNone(patient.cpf)


class PatientAccessTests(TestCase):
    def test_professional_only_sees_assigned_patients(self):
        professional = Professional.objects.create(full_name="Dra. Teste", specialty=Professional.Specialty.PILATES)
        assigned = Patient.objects.create(full_name="Paciente Vinculado")
        other = Patient.objects.create(full_name="Paciente Outro")
        ProfessionalPatientAssignment.objects.create(patient=assigned, professional=professional)
        user = get_user_model().objects.create_user(username="prof", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patients:list"))

        self.assertContains(response, assigned.full_name)
        self.assertNotContains(response, other.full_name)

    def test_professional_record_only_shows_own_notes_by_patient(self):
        patient = Patient.objects.create(full_name="Paciente Prontuario")
        professional = Professional.objects.create(full_name="Dra. Uma", specialty=Professional.Specialty.PILATES)
        other_professional = Professional.objects.create(
            full_name="Dra. Outra",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
        )
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=other_professional)
        own_note = ProfessionalNote.objects.create(
            patient=patient,
            professional=professional,
            title="Evolucao visivel",
            body="Conteudo do profissional logado.",
        )
        ProfessionalNote.objects.create(
            patient=patient,
            professional=other_professional,
            title="Evolucao sigilosa",
            body="Conteudo de outro profissional.",
        )
        user = get_user_model().objects.create_user(username="prof-prontuario", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patients:patient_notes", args=[patient.pk]))

        self.assertContains(response, own_note.title)
        self.assertNotContains(response, "Evolucao sigilosa")

    def test_professional_cannot_edit_note_from_another_professional(self):
        patient = Patient.objects.create(full_name="Paciente Edicao")
        professional = Professional.objects.create(full_name="Dra. Dona", specialty=Professional.Specialty.PILATES)
        other_professional = Professional.objects.create(
            full_name="Dra. Autora",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
        )
        ProfessionalPatientAssignment.objects.create(patient=patient, professional=professional)
        note = ProfessionalNote.objects.create(
            patient=patient,
            professional=other_professional,
            title="Nao editar",
            body="Restrito ao autor.",
        )
        user = get_user_model().objects.create_user(username="prof-sem-acesso", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": professional},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patients:note_update", args=[patient.pk, note.pk]))

        self.assertEqual(response.status_code, 404)
