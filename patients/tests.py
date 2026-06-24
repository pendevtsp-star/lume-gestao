from django.core.exceptions import ValidationError
from django.test import TestCase

from patients.models import Patient


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
