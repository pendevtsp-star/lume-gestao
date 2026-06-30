from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from patients.models import Patient, ProfessionalPatientAssignment
from team.forms import ProfessionalForm
from team.models import Employee, Professional


class TeamDeleteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="gerente-equipe", password="Senha@123")
        UserProfile.objects.update_or_create(user=self.user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(self.user)

    def test_management_can_soft_delete_employee_from_web(self):
        employee = Employee.objects.create(full_name="Funcionario Excluir", role=Employee.Role.RECEPTION)

        response = self.client.post(reverse("team:employee_delete", args=[employee.pk]))

        employee.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(employee.active)

    def test_management_can_soft_delete_professional_from_web(self):
        professional = Professional.objects.create(
            full_name="Profissional Excluir",
            specialty=Professional.Specialty.PILATES,
        )

        response = self.client.post(reverse("team:professional_delete", args=[professional.pk]))

        professional.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertFalse(professional.active)

    def test_employee_api_destroy_soft_deletes_employee(self):
        employee = Employee.objects.create(full_name="Funcionario API Excluir", role=Employee.Role.FINANCE)

        response = self.client.delete(f"/api/v1/employees/{employee.pk}/")

        employee.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertFalse(employee.active)

    def test_professional_api_destroy_soft_deletes_professional(self):
        professional = Professional.objects.create(
            full_name="Profissional API Excluir",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
        )

        response = self.client.delete(f"/api/v1/professionals/{professional.pk}/")

        professional.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertFalse(professional.active)

    def test_professional_form_syncs_multiple_patients(self):
        patient_one = Patient.objects.create(full_name="Paciente Um")
        patient_two = Patient.objects.create(full_name="Paciente Dois")
        form = ProfessionalForm(
            data={
                "full_name": "Dra. Vinculos",
                "specialty": Professional.Specialty.PILATES,
                "registration_number": "",
                "phone": "",
                "email": "",
                "bio": "",
                "active": "on",
                "assigned_patients": [str(patient_one.pk), str(patient_two.pk)],
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        professional = form.save()
        form.save_patient_assignments(professional)

        self.assertEqual(
            ProfessionalPatientAssignment.objects.filter(professional=professional, active=True).count(),
            2,
        )
