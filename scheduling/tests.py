from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Membership, ServicePlan
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage, ServiceUsage
from scheduling.slots import generate_available_slots
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

    def test_appointment_must_follow_availability_when_defined(self):
        day = timezone.localdate() + timedelta(days=1)
        start = timezone.make_aware(datetime.combine(day, time(14, 0)))
        ProfessionalAvailability.objects.create(
            professional=self.professional,
            weekday=start.weekday(),
            starts_at=time(8, 0),
            ends_at=time(12, 0),
            valid_from=start.date(),
        )
        appointment = Appointment(
            patient=self.patient,
            professional=self.professional,
            starts_at=start.replace(hour=14, minute=0),
            ends_at=start.replace(hour=15, minute=0),
        )

        with self.assertRaises(ValidationError):
            appointment.full_clean()

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

    def test_cancel_does_not_consume_package(self):
        user = get_user_model().objects.create_user(username="paciente-cancelar", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        package = ServicePackage.objects.create(membership=self.membership, total_sessions=4, used_sessions=1)
        start = timezone.now() + timedelta(days=2)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            service_units=1,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("scheduling:appointment_cancel", args=[appointment.pk]))

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        package.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELED)
        self.assertEqual(package.used_sessions, 1)
        self.assertFalse(ServiceUsage.objects.filter(appointment=appointment).exists())

    def test_reschedule_marks_original_and_creates_new_without_consuming_package(self):
        user = get_user_model().objects.create_user(username="paciente-reagendar", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        package = ServicePackage.objects.create(membership=self.membership, total_sessions=4, used_sessions=1)
        day = timezone.localdate() + timedelta(days=3)
        new_day = day + timedelta(days=1)
        start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        new_start = timezone.make_aware(datetime.combine(new_day, time(10, 0)))
        ProfessionalAvailability.objects.create(
            professional=self.professional,
            weekday=new_day.weekday(),
            starts_at=time(8, 0),
            ends_at=time(12, 0),
            valid_from=new_day,
        )
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            service_units=1,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:appointment_reschedule", args=[appointment.pk]),
            {
                "professional": self.professional.pk,
                "appointment_date": new_day.isoformat(),
                "duration_minutes": "60",
                "selected_start": new_start.strftime("%H:%M"),
                "notes": "Novo horario solicitado.",
            },
        )

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        package.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.RESCHEDULED)
        self.assertEqual(package.used_sessions, 1)
        self.assertTrue(
            Appointment.objects.filter(
                patient=self.patient,
                rescheduled_from=appointment,
                status=Appointment.Status.REQUESTED,
            ).exists()
        )

    def test_available_slots_skip_occupied_times(self):
        day = timezone.localdate() + timedelta(days=5)
        occupied_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        ProfessionalAvailability.objects.create(
            professional=self.professional,
            weekday=day.weekday(),
            starts_at=time(8, 0),
            ends_at=time(11, 0),
            valid_from=day,
        )
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=occupied_start,
            ends_at=occupied_start + timedelta(hours=1),
        )

        labels = [slot["label"] for slot in generate_available_slots(self.professional, day, 60)]

        self.assertEqual(labels, ["08:00 - 09:00", "10:00 - 11:00"])

    def test_patient_create_view_lists_only_free_slots(self):
        user = get_user_model().objects.create_user(username="paciente-slots", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        day = timezone.localdate() + timedelta(days=6)
        occupied_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        ProfessionalAvailability.objects.create(
            professional=self.professional,
            weekday=day.weekday(),
            starts_at=time(8, 0),
            ends_at=time(11, 0),
            valid_from=day,
        )
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=occupied_start,
            ends_at=occupied_start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("scheduling:appointment_create"),
            {
                "patient": self.patient.pk,
                "professional": self.professional.pk,
                "appointment_date": day.isoformat(),
                "duration_minutes": "60",
                "service_units": "1",
            },
        )

        self.assertContains(response, "08:00 - 09:00")
        self.assertContains(response, "10:00 - 11:00")
        self.assertNotContains(response, "09:00 - 10:00")

    def test_patient_can_create_requested_appointment_from_free_slot(self):
        user = get_user_model().objects.create_user(username="paciente-cria-slot", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        day = timezone.localdate() + timedelta(days=7)
        ProfessionalAvailability.objects.create(
            professional=self.professional,
            weekday=day.weekday(),
            starts_at=time(8, 0),
            ends_at=time(11, 0),
            valid_from=day,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "patient": self.patient.pk,
                "professional": self.professional.pk,
                "appointment_date": day.isoformat(),
                "duration_minutes": "60",
                "service_units": "1",
                "selected_start": "08:00",
                "notes": "Solicitado pelo portal.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Appointment.objects.filter(
                patient=self.patient,
                professional=self.professional,
                status=Appointment.Status.REQUESTED,
                booking_source=Appointment.BookingSource.PATIENT,
                notes="Solicitado pelo portal.",
            ).exists()
        )
