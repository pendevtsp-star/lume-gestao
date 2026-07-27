from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import UserProfile
from patients.models import Patient, ProfessionalPatientAssignment
from patients.selectors import patient_ids_visible_to_professional, patients_visible_to_user
from team.models import Professional


class PatientVisibilitySelectorTests(TestCase):
    def setUp(self):
        self.assigned_patient = Patient.objects.create(full_name="Paciente vinculada")
        self.appointment_patient = Patient.objects.create(full_name="Paciente com atendimento")
        self.other_patient = Patient.objects.create(full_name="Paciente sem vinculo")
        self.professional = Professional.objects.create(
            full_name="Profissional teste",
            specialty=Professional.Specialty.PILATES,
        )
        ProfessionalPatientAssignment.objects.create(
            patient=self.assigned_patient,
            professional=self.professional,
        )

        from scheduling.models import Appointment

        starts_at = timezone.now() + timedelta(days=1)
        Appointment.objects.create(
            patient=self.appointment_patient,
            professional=self.professional,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

    def create_user(self, username, role, **profile_fields):
        user = get_user_model().objects.create_user(username=username, password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": role, **profile_fields},
        )
        return user

    def test_backoffice_roles_can_see_all_patients(self):
        for role in (
            UserProfile.Role.ADMINISTRATION,
            UserProfile.Role.MANAGEMENT,
            UserProfile.Role.VIEWER,
        ):
            with self.subTest(role=role):
                user = self.create_user(f"user-{role}", role)
                self.assertCountEqual(
                    patients_visible_to_user(user).values_list("pk", flat=True),
                    [self.assigned_patient.pk, self.appointment_patient.pk, self.other_patient.pk],
                )

    def test_patient_sees_only_own_record(self):
        user = self.create_user(
            "patient-user",
            UserProfile.Role.PATIENT,
            patient=self.assigned_patient,
        )

        self.assertQuerySetEqual(
            patients_visible_to_user(user),
            [self.assigned_patient],
        )

    def test_professional_sees_assignment_and_appointment_links(self):
        user = self.create_user(
            "professional-user",
            UserProfile.Role.PROFESSIONAL,
            professional=self.professional,
        )

        self.assertCountEqual(
            patients_visible_to_user(user).values_list("pk", flat=True),
            [self.assigned_patient.pk, self.appointment_patient.pk],
        )
        self.assertCountEqual(
            patient_ids_visible_to_professional(self.professional),
            [self.assigned_patient.pk, self.appointment_patient.pk],
        )

    def test_user_without_supported_profile_link_sees_nothing(self):
        user = self.create_user("unlinked-patient", UserProfile.Role.PATIENT)

        self.assertFalse(patients_visible_to_user(user).exists())
