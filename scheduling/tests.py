from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase
from django.test import skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Membership, ServicePlan
from core.models import ClinicSettings
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment, AppointmentSeries, ProfessionalAvailability, ServicePackage, ServiceUsage
from scheduling.slots import generate_available_slots
from team.models import Professional


class SchedulingTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(full_name="Paciente Agenda")
        self.patient_two = Patient.objects.create(full_name="Paciente Grupo")
        self.professional = Professional.objects.create(
            full_name="Profissional Agenda",
            specialty=Professional.Specialty.PILATES,
        )
        ProfessionalPatientAssignment.objects.create(patient=self.patient, professional=self.professional)
        ProfessionalPatientAssignment.objects.create(patient=self.patient_two, professional=self.professional)
        self.plan = ServicePlan.objects.create(
            name="Plano Agenda",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("400.00"),
            sessions_per_week=2,
        )
        self.membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        self.membership_two = Membership.objects.create(patient=self.patient_two, plan=self.plan, due_day=10)
        today = timezone.localdate()
        for weekday in range(7):
            ProfessionalAvailability.objects.create(
                professional=self.professional,
                weekday=weekday,
                starts_at=time(8, 0),
                ends_at=time(18, 0),
                valid_from=today,
                session_capacity=1,
            )

    def test_appointment_rejects_professional_partial_overlap(self):
        start = timezone.now() + timedelta(days=1)
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        overlapping = Appointment(
            patient=self.patient_two,
            professional=self.professional,
            starts_at=start + timedelta(minutes=30),
            ends_at=start + timedelta(hours=2),
        )

        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_group_session_allows_same_exact_slot_with_capacity(self):
        day = timezone.localdate() + timedelta(days=1)
        start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            slot_capacity=2,
        )
        grouped = Appointment(
            patient=self.patient_two,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            slot_capacity=2,
        )

        grouped.full_clean()
        grouped.save()

        self.assertTrue(grouped.slot_group)
        self.assertEqual(
            Appointment.objects.filter(
                professional=self.professional,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                status__in=[Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED],
            ).count(),
            2,
        )

    def test_appointment_must_follow_availability_when_defined(self):
        day = timezone.localdate() + timedelta(days=1)
        start = timezone.make_aware(datetime.combine(day, time(20, 0)))
        appointment = Appointment(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
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

    def test_appointment_save_creates_backend_assignment(self):
        ProfessionalPatientAssignment.objects.filter(patient=self.patient, professional=self.professional).delete()
        start = timezone.now() + timedelta(days=1)

        with self.captureOnCommitCallbacks(execute=True):
            Appointment.objects.create(
                patient=self.patient,
                professional=self.professional,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
            )

        self.assertTrue(
            ProfessionalPatientAssignment.objects.filter(
                patient=self.patient,
                professional=self.professional,
                active=True,
            ).exists()
        )

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

    def test_patient_cannot_reschedule_inside_configured_deadline(self):
        settings = ClinicSettings.load()
        settings.rescheduling_deadline_hours = 48
        settings.save()
        user = get_user_model().objects.create_user(username="paciente-reagendar-prazo", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        start = timezone.now() + timedelta(hours=24)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("scheduling:appointment_reschedule", args=[appointment.pk]))

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.SCHEDULED)

    def test_available_slots_keep_group_slots_with_remaining_capacity(self):
        ProfessionalAvailability.objects.all().delete()
        day = timezone.localdate() + timedelta(days=5)
        occupied_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        ProfessionalAvailability.objects.create(
            professional=self.professional,
            weekday=day.weekday(),
            starts_at=time(8, 0),
            ends_at=time(11, 0),
            valid_from=day,
            session_capacity=1,
        )
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=occupied_start,
            ends_at=occupied_start + timedelta(hours=1),
            slot_capacity=2,
        )

        slots = generate_available_slots(self.professional, day, 60)
        slot_by_label = {slot["label"]: slot for slot in slots}

        self.assertIn("09:00 - 10:00", slot_by_label)
        self.assertEqual(slot_by_label["09:00 - 10:00"]["remaining_capacity"], 1)

    def test_patient_create_view_lists_only_slots_with_capacity(self):
        user = get_user_model().objects.create_user(username="paciente-slots", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        ProfessionalAvailability.objects.all().delete()
        day = timezone.localdate() + timedelta(days=6)
        occupied_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        ProfessionalAvailability.objects.create(
            professional=self.professional,
            weekday=day.weekday(),
            starts_at=time(8, 0),
            ends_at=time(11, 0),
            valid_from=day,
            session_capacity=1,
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
                "patients": [self.patient.pk],
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
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "patients": [self.patient.pk],
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

    def test_management_can_create_recurring_group_series(self):
        user = get_user_model().objects.create_user(username="gestao-recorrencia", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        day = timezone.localdate() + timedelta(days=7)
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "patients": [self.patient.pk, self.patient_two.pk],
                "professional": self.professional.pk,
                "appointment_date": day.isoformat(),
                "duration_minutes": "60",
                "service_units": "1",
                "session_capacity": "2",
                "repeat_mode": "weekly",
                "repeat_interval_weeks": "1",
                "repeat_count": "3",
                "selected_start": "09:00",
                "notes": "Turma semanal.",
            },
        )

        self.assertEqual(response.status_code, 302)
        series = AppointmentSeries.objects.get()
        self.assertEqual(series.occurrences_count, 3)
        self.assertEqual(
            Appointment.objects.filter(series=series, professional=self.professional).count(),
            6,
        )
        self.assertEqual(
            Appointment.objects.filter(series=series, slot_capacity=2, status=Appointment.Status.SCHEDULED).count(),
            6,
        )

    def test_professional_can_confirm_requested_appointment(self):
        user = get_user_model().objects.create_user(username="prof-confirma", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": self.professional},
        )
        day = timezone.localdate() + timedelta(days=4)
        start = timezone.make_aware(datetime.combine(day, time(10, 0)))
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            status=Appointment.Status.REQUESTED,
            booking_source=Appointment.BookingSource.PATIENT,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("scheduling:appointment_confirm", args=[appointment.pk]))

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.SCHEDULED)

    def test_management_can_reschedule_current_and_future_series(self):
        user = get_user_model().objects.create_user(username="gestao-reagenda-serie", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        day = timezone.localdate() + timedelta(days=10)
        series = AppointmentSeries.objects.create(
            created_by=user,
            interval_weeks=1,
            repeat_until=day + timedelta(weeks=1),
            occurrences_count=2,
        )
        first_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        second_start = first_start + timedelta(weeks=1)
        first = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=first_start,
            ends_at=first_start + timedelta(hours=1),
            series=series,
        )
        second = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=second_start,
            ends_at=second_start + timedelta(hours=1),
            series=series,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:appointment_reschedule", args=[first.pk]),
            {
                "professional": self.professional.pk,
                "appointment_date": (day + timedelta(days=2)).isoformat(),
                "duration_minutes": "60",
                "reschedule_scope": "current_and_future",
                "selected_start": "10:00",
                "notes": "Mudanca definitiva de horario.",
            },
        )

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, Appointment.Status.RESCHEDULED)
        self.assertEqual(second.status, Appointment.Status.RESCHEDULED)
        replacements = Appointment.objects.filter(rescheduled_from__in=[first, second]).order_by("starts_at")
        self.assertEqual(replacements.count(), 2)
        self.assertTrue(all(appointment.status == Appointment.Status.SCHEDULED for appointment in replacements))
        self.assertNotEqual(replacements.first().series_id, series.pk)
    def test_api_rejects_overlapping_appointment_in_backend_validation(self):
        user = get_user_model().objects.create_user(username="gestao-api-agenda", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        start = timezone.now() + timedelta(days=10)
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.post(
            "/api/v1/appointments/",
            {
                "patient": self.patient_two.pk,
                "professional": self.professional.pk,
                "starts_at": (start + timedelta(minutes=30)).isoformat(),
                "ends_at": (start + timedelta(hours=1, minutes=30)).isoformat(),
                "status": Appointment.Status.SCHEDULED,
                "booking_source": Appointment.BookingSource.MANAGEMENT,
                "service_units": 1,
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_patient_cannot_patch_appointment_directly_api(self):
        user = get_user_model().objects.create_user(username="paciente-api-patch-agenda", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        start = timezone.now() + timedelta(days=10)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.patch(
            f"/api/v1/appointments/{appointment.pk}/",
            {"status": Appointment.Status.COMPLETED},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        appointment.refresh_from_db()
        self.assertNotEqual(appointment.status, Appointment.Status.COMPLETED)

    def test_patient_cannot_create_service_package_api(self):
        user = get_user_model().objects.create_user(username="paciente-api-pacote", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        self.client.force_login(user)

        response = self.client.post(
            "/api/v1/service-packages/",
            {
                "membership": self.membership.pk,
                "total_sessions": 99,
                "used_sessions": 0,
                "status": ServicePackage.Status.ACTIVE,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ServicePackage.objects.filter(total_sessions=99).exists())

    def test_management_can_soft_delete_service_package_from_web(self):
        user = get_user_model().objects.create_user(username="gestao-excluir-pacote", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        package = ServicePackage.objects.create(membership=self.membership, total_sessions=6)
        self.client.force_login(user)

        response = self.client.post(reverse("scheduling:package_delete", args=[package.pk]))

        package.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(package.status, ServicePackage.Status.CANCELED)
        list_response = self.client.get(reverse("scheduling:packages"))
        self.assertNotContains(list_response, self.patient.full_name)

    def test_service_package_api_destroy_cancels_package(self):
        user = get_user_model().objects.create_user(username="gestao-api-excluir-pacote", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        package = ServicePackage.objects.create(membership=self.membership, total_sessions=6)
        self.client.force_login(user)

        response = self.client.delete(f"/api/v1/service-packages/{package.pk}/")

        package.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(package.status, ServicePackage.Status.CANCELED)

    def test_professional_cannot_register_usage_for_other_professional_api(self):
        other_professional = Professional.objects.create(
            full_name="Profissional Baixa Outro",
            specialty=Professional.Specialty.PILATES,
        )
        user = get_user_model().objects.create_user(username="prof-api-baixa", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": self.professional},
        )
        package = ServicePackage.objects.create(membership=self.membership, total_sessions=4, used_sessions=0)
        start = timezone.now() + timedelta(days=11)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=other_professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.post(
            "/api/v1/service-usages/",
            {
                "service_package": package.pk,
                "appointment": appointment.pk,
                "units": 1,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ServiceUsage.objects.filter(appointment=appointment).exists())

    def test_professional_can_register_usage_for_own_appointment_api(self):
        user = get_user_model().objects.create_user(username="prof-api-baixa-propria", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": self.professional},
        )
        package = ServicePackage.objects.create(membership=self.membership, total_sessions=4, used_sessions=0)
        start = timezone.now() + timedelta(days=12)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.post(
            "/api/v1/service-usages/",
            {
                "service_package": package.pk,
                "appointment": appointment.pk,
                "units": 1,
            },
        )

        self.assertEqual(response.status_code, 201)
        usage = ServiceUsage.objects.get(appointment=appointment)
        appointment.refresh_from_db()
        package.refresh_from_db()
        self.assertEqual(usage.registered_by, user)
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)
        self.assertEqual(package.used_sessions, 1)

    def test_professional_cannot_create_availability_for_another_professional_api(self):
        other_professional = Professional.objects.create(
            full_name="Profissional Outro API",
            specialty=Professional.Specialty.PILATES,
        )
        user = get_user_model().objects.create_user(username="prof-api-disponibilidade", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": self.professional},
        )
        self.client.force_login(user)

        response = self.client.post(
            "/api/v1/professional-availabilities/",
            {
                "professional": other_professional.pk,
                "weekday": 1,
                "starts_at": "08:00",
                "ends_at": "12:00",
                "session_capacity": 2,
                "valid_from": timezone.localdate().isoformat(),
                "active": True,
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_calendar_week_view_and_ics_export_are_available(self):
        user = get_user_model().objects.create_user(username="gestao-calendario", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        start = timezone.now() + timedelta(days=1)
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            slot_capacity=2,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("scheduling:appointments"))
        self.assertContains(response, "Sessoes em grupo")
        self.assertContains(response, self.patient.full_name)

        ics_response = self.client.get(reverse("scheduling:appointments_ical"))
        self.assertEqual(ics_response.status_code, 200)
        self.assertIn("text/calendar", ics_response["Content-Type"])
        self.assertIn("BEGIN:VCALENDAR", ics_response.content.decode())


@skipUnlessDBFeature("has_select_for_update")
class SchedulingTransactionTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="gestao-transacao", password="Senha@123")
        self.patient = Patient.objects.create(full_name="Paciente Transacao", phone="11999990000")
        self.second_patient = Patient.objects.create(full_name="Paciente Serie", phone="11999990001")
        self.professional = Professional.objects.create(
            full_name="Profissional Transacao",
            specialty=Professional.Specialty.PILATES,
        )
        ProfessionalPatientAssignment.objects.create(patient=self.patient, professional=self.professional)
        ProfessionalPatientAssignment.objects.create(patient=self.second_patient, professional=self.professional)
        UserProfile.objects.update_or_create(user=self.user, defaults={"role": UserProfile.Role.MANAGEMENT})
        today = timezone.localdate()
        for weekday in range(7):
            ProfessionalAvailability.objects.create(
                professional=self.professional,
                weekday=weekday,
                starts_at=time(8, 0),
                ends_at=time(18, 0),
                valid_from=today,
                session_capacity=2,
            )
        self.client.force_login(self.user)

    def test_recurring_reschedule_keeps_series_update_inside_transaction(self):
        start_day = timezone.localdate() + timedelta(days=7)
        next_day = start_day + timedelta(days=7)
        first_start = timezone.make_aware(datetime.combine(start_day, time(9, 0)))
        second_start = timezone.make_aware(datetime.combine(next_day, time(9, 0)))
        series = AppointmentSeries.objects.create(
            created_by=self.user,
            repeat_type=AppointmentSeries.RepeatType.WEEKLY,
            interval_weeks=1,
            repeat_until=next_day,
            occurrences_count=2,
        )
        first = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=first_start,
            ends_at=first_start + timedelta(hours=1),
            series=series,
        )
        second = Appointment.objects.create(
            patient=self.second_patient,
            professional=self.professional,
            starts_at=second_start,
            ends_at=second_start + timedelta(hours=1),
            series=series,
        )

        response = self.client.post(
            reverse("scheduling:appointment_reschedule", args=[first.pk]),
            {
                "professional": self.professional.pk,
                "appointment_date": start_day.isoformat(),
                "duration_minutes": "60",
                "selected_start": "10:00",
                "reschedule_scope": "current_and_future",
                "notes": "Mudanca definitiva de horario.",
            },
        )

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, Appointment.Status.RESCHEDULED)
        self.assertEqual(second.status, Appointment.Status.RESCHEDULED)
        self.assertEqual(Appointment.objects.filter(rescheduled_from__in=[first, second]).count(), 2)
