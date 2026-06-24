from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Membership, ServicePlan
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment, ServicePackage, ServiceUsage
from team.models import Professional


class SchedulingTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(full_name="Paciente Agenda")
        self.professional = Professional.objects.create(
            full_name="Profissional Agenda",
            specialty=Professional.Specialty.PILATES,
        )
        ProfessionalPatientAssignment.objects.create(patient=self.patient, professional=self.professional)
        self.plan = ServicePlan.objects.create(
            name="Plano Agenda",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("400.00"),
            sessions_per_week=2,
        )
        self.membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)

    def test_appointment_rejects_professional_overlap(self):
        start = timezone.now() + timedelta(days=1)
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        overlapping = Appointment(
            patient=self.patient,
            professional=self.professional,
            starts_at=start + timedelta(minutes=30),
            ends_at=start + timedelta(hours=2),
        )

        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_complete_appointment_consumes_package(self):
        user = get_user_model().objects.create_user(username="prof-agenda", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": self.professional},
        )
        package = ServicePackage.objects.create(
            membership=self.membership,
            total_sessions=4,
            used_sessions=1,
        )
        start = timezone.now() + timedelta(days=1)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            service_units=1,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("scheduling:appointment_complete", args=[appointment.pk]))

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        package.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)
        self.assertEqual(package.used_sessions, 2)
        self.assertTrue(ServiceUsage.objects.filter(appointment=appointment).exists())
