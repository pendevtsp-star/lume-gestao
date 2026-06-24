from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from patients.models import Patient
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
