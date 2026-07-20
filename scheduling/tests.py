from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase
from django.test import skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Membership, Payment, ServicePlan
from core.models import ClinicSettings
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import (
    Appointment,
    AppointmentAttendance,
    AppointmentSeries,
    PatientCheckIn,
    PatientGoal,
    PatientNotification,
    PatientNotificationPreference,
    OperationalCalendarEvent,
    ProfessionalAvailability,
    RescheduleRequest,
    ServicePackage,
    ServicePackageAdjustment,
    ServiceUsage,
)
from scheduling.forms import ServicePackageForm
from scheduling.services import generate_operational_notifications
from scheduling.slots import generate_available_slots, slot_is_available
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

    def test_complete_appointment_can_add_credit_when_confirmed(self):
        user = get_user_model().objects.create_user(username="prof-agenda-credito-extra", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": self.professional},
        )
        ServicePackage.objects.create(
            membership=self.membership,
            total_sessions=1,
            used_sessions=1,
            status=ServicePackage.Status.FINISHED,
        )
        start = timezone.now() + timedelta(days=1)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            service_plan=self.plan,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            service_units=1,
        )
        self.client.force_login(user)

        response_without_confirmation = self.client.post(reverse("scheduling:appointment_complete", args=[appointment.pk]))
        appointment.refresh_from_db()
        self.assertEqual(response_without_confirmation.status_code, 302)
        self.assertEqual(appointment.status, Appointment.Status.SCHEDULED)
        self.assertFalse(ServiceUsage.objects.filter(appointment=appointment).exists())

        response = self.client.post(
            reverse("scheduling:appointment_complete", args=[appointment.pk]),
            {"add_credit": "1"},
        )

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)
        usage = ServiceUsage.objects.get(appointment=appointment)
        adjustment = ServicePackageAdjustment.objects.get(appointment=appointment)
        self.assertEqual(adjustment.delta_sessions, 1)
        self.assertEqual(adjustment.reason, ServicePackageAdjustment.Reason.APPOINTMENT_NO_CREDIT)
        self.assertEqual(usage.service_package, adjustment.service_package)

    def test_complete_appointment_consumes_matching_service_plan_package(self):
        user = get_user_model().objects.create_user(username="prof-agenda-servico", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": self.professional},
        )
        massage_plan = ServicePlan.objects.create(
            name="Massagem avulsa",
            category=ServicePlan.Category.MASSAGE,
            plan_type=ServicePlan.PlanType.SINGLE,
            monthly_price=Decimal("120.00"),
            sessions_per_week=1,
            included_sessions=1,
        )
        massage_membership = Membership.objects.create(patient=self.patient, plan=massage_plan, due_day=10)
        pilates_package = ServicePackage.objects.create(membership=self.membership, total_sessions=8, used_sessions=0)
        massage_package = ServicePackage.objects.create(membership=massage_membership, total_sessions=1, used_sessions=0)
        start = timezone.now() + timedelta(days=1)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            service_plan=massage_plan,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            service_units=1,
        )
        self.client.force_login(user)

        response = self.client.post(reverse("scheduling:appointment_complete", args=[appointment.pk]))

        self.assertEqual(response.status_code, 302)
        pilates_package.refresh_from_db()
        massage_package.refresh_from_db()
        self.assertEqual(pilates_package.used_sessions, 0)
        self.assertEqual(massage_package.used_sessions, 1)

    def test_service_package_form_inherits_plan_defaults(self):
        plan = ServicePlan.objects.create(
            name="Pilates Trimestral",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("900.00"),
            duration_months=3,
            sessions_per_week=2,
            included_sessions=24,
        )
        form = ServicePackageForm(
            data={
                "patient": self.patient.pk,
                "plan": plan.pk,
                "starts_on": "2026-06-15",
                "status": ServicePackage.Status.ACTIVE,
                "notes": "Adesao inicial.",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        package = form.save()

        self.assertEqual(package.total_sessions, 24)
        self.assertEqual(package.used_sessions, 0)
        self.assertEqual(package.expires_on, date(2026, 9, 15))
        self.assertEqual(package.membership.plan, plan)

    def test_service_package_form_can_register_paid_cycle_payment(self):
        plan = ServicePlan.objects.create(
            name="Pilates Semestral",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("1800.00"),
            duration_months=6,
            sessions_per_week=2,
            included_sessions=48,
        )
        form = ServicePackageForm(
            data={
                "patient": self.patient.pk,
                "plan": plan.pk,
                "starts_on": "2026-06-15",
                "status": ServicePackage.Status.ACTIVE,
                "payment_mode": ServicePackageForm.PaymentMode.PAID_NOW,
                "payment_method": Payment.Method.PIX,
                "paid_at": "2026-06-15",
                "notes": "Adesao paga na recepcao.",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        package = form.save()
        payment = Payment.objects.get(membership=package.membership, reference_month=date(2026, 6, 1))

        self.assertEqual(package.total_sessions, 48)
        self.assertEqual(package.expires_on, date(2026, 12, 15))
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.amount, Decimal("1800.00"))
        self.assertEqual(payment.paid_at, date(2026, 6, 15))

    def test_service_package_form_can_register_pending_cycle_payment(self):
        plan = ServicePlan.objects.create(
            name="Pilates Mensal",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("500.00"),
            duration_months=1,
            sessions_per_week=2,
            included_sessions=8,
        )
        form = ServicePackageForm(
            data={
                "patient": self.patient.pk,
                "plan": plan.pk,
                "starts_on": "2026-06-15",
                "status": ServicePackage.Status.ACTIVE,
                "payment_mode": ServicePackageForm.PaymentMode.PENDING,
                "payment_method": Payment.Method.PIX,
                "notes": "Gerar cobrança presencial.",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        package = form.save()
        payment = Payment.objects.get(membership=package.membership, reference_month=date(2026, 6, 1))

        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNone(payment.paid_at)
        self.assertEqual(payment.amount, Decimal("500.00"))

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
        expected_week = new_day - timedelta(days=new_day.weekday())
        self.assertIn(f"semana={expected_week.isoformat()}", response["Location"])
        self.assertIn(f"dia={new_day.isoformat()}", response["Location"])
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

    def test_reschedule_form_reuses_duration_without_showing_it(self):
        user = get_user_model().objects.create_user(username="gestao-reagendar-simples", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        start = timezone.now() + timedelta(days=5)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(minutes=60),
            service_units=1,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("scheduling:appointment_reschedule", args=[appointment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Duracao")
        self.assertContains(response, 'name="duration_minutes"', html=False)

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

    def test_group_capacity_comes_from_professional_availability(self):
        user = get_user_model().objects.create_user(username="gestao-capacidade-auto", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        day = timezone.localdate() + timedelta(days=8)
        ProfessionalAvailability.objects.filter(
            professional=self.professional,
            weekday=day.weekday(),
        ).update(session_capacity=6)
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "patients": [self.patient.pk, self.patient_two.pk],
                "professional": self.professional.pk,
                "appointment_date": day.isoformat(),
                "duration_minutes": "60",
                "service_units": "1",
                "repeat_mode": "none",
                "selected_start": "09:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Appointment.objects.filter(slot_capacity=6).count(), 2)

        agenda_response = self.client.get(reverse("scheduling:appointments"), {"semana": day.isoformat()})
        self.assertContains(agenda_response, "Sessao em grupo")
        self.assertContains(agenda_response, "2/6 alunos")

    def test_group_session_modal_lists_all_patients_with_individual_actions(self):
        user = get_user_model().objects.create_user(username="gestao-modal-grupo", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        third_patient = Patient.objects.create(full_name="Paciente Cascata")
        ProfessionalPatientAssignment.objects.create(patient=third_patient, professional=self.professional)
        day = timezone.localdate() + timedelta(days=8)
        start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        group_appointments = [
            Appointment.objects.create(
                patient=patient,
                professional=self.professional,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                slot_capacity=6,
                slot_group="grupo-modal",
            )
            for patient in [self.patient, self.patient_two, third_patient]
        ]
        self.client.force_login(user)

        response = self.client.get(reverse("scheduling:appointments"), {"semana": day.isoformat()})

        self.assertContains(response, "3 confirmada(s) de 6 vaga(s)")
        self.assertContains(response, "Cada acao abaixo vale apenas para a paciente escolhida")
        for appointment in group_appointments:
            self.assertContains(response, appointment.patient.full_name)
            self.assertContains(response, reverse("scheduling:appointment_reschedule", args=[appointment.pk]))

    def test_reschedule_to_existing_group_slot_uses_target_group(self):
        user = get_user_model().objects.create_user(username="gestao-reagenda-grupo-alvo", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        day = timezone.localdate() + timedelta(days=8)
        source_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        target_start = timezone.make_aware(datetime.combine(day, time(10, 0)))
        source = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=source_start,
            ends_at=source_start + timedelta(hours=1),
            slot_capacity=4,
            slot_group="grupo-origem",
        )
        target = Appointment.objects.create(
            patient=self.patient_two,
            professional=self.professional,
            starts_at=target_start,
            ends_at=target_start + timedelta(hours=1),
            slot_capacity=4,
            slot_group="grupo-destino",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:appointment_reschedule", args=[source.pk]),
            {
                "professional": self.professional.pk,
                "appointment_date": day.isoformat(),
                "duration_minutes": "60",
                "selected_start": "10:00",
                "notes": "Mudanca para grupo existente.",
            },
        )

        self.assertEqual(response.status_code, 302)
        source.refresh_from_db()
        target.refresh_from_db()
        replacement = Appointment.objects.get(rescheduled_from=source)
        self.assertEqual(source.status, Appointment.Status.RESCHEDULED)
        self.assertEqual(target.status, Appointment.Status.SCHEDULED)
        self.assertEqual(replacement.starts_at, target_start)
        self.assertEqual(replacement.slot_group, target.slot_group)
        self.assertEqual(replacement.slot_capacity, target.slot_capacity)

    def test_reschedule_lists_existing_group_slot_with_capacity_even_after_availability_changes(self):
        user = get_user_model().objects.create_user(username="gestao-reagenda-grupo-fora-janela", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        day = timezone.localdate() + timedelta(days=8)
        ProfessionalAvailability.objects.filter(professional=self.professional, weekday=day.weekday()).update(
            starts_at=time(8, 0),
            ends_at=time(18, 0),
            session_capacity=4,
        )
        source_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        target_start = timezone.make_aware(datetime.combine(day, time(7, 0)))
        source = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=source_start,
            ends_at=source_start + timedelta(hours=1),
            slot_capacity=4,
            slot_group="grupo-origem-7h",
        )
        target_group = "grupo-destino-7h"
        for patient in [self.patient_two, Patient.objects.create(full_name="Paciente Terceira"), Patient.objects.create(full_name="Paciente Quarta")]:
            Appointment.objects.create(
                patient=patient,
                professional=self.professional,
                starts_at=target_start,
                ends_at=target_start + timedelta(hours=1),
                slot_capacity=4,
                slot_group=target_group,
            )
        self.client.force_login(user)

        slots = generate_available_slots(self.professional, day, 60, exclude_appointment=source)
        target_slot = next((slot for slot in slots if slot["start_value"] == "07:00"), None)
        self.assertIsNotNone(target_slot)
        self.assertTrue(target_slot["group_slot"])
        self.assertEqual(target_slot["remaining_capacity"], 1)

        response = self.client.post(
            reverse("scheduling:appointment_reschedule", args=[source.pk]),
            {
                "professional": self.professional.pk,
                "appointment_date": day.isoformat(),
                "duration_minutes": "60",
                "selected_start": "07:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        replacement = Appointment.objects.get(rescheduled_from=source)
        self.assertEqual(replacement.starts_at, target_start)
        self.assertEqual(replacement.slot_group, target_group)
        self.assertEqual(replacement.slot_capacity, 4)

    def test_reschedule_uses_the_same_capacity_rule_shown_in_available_slots(self):
        user = get_user_model().objects.create_user(username="gestao-capacidade-unificada", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        day = timezone.localdate() + timedelta(days=8)
        ProfessionalAvailability.objects.filter(professional=self.professional, weekday=day.weekday()).update(session_capacity=4)
        source_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        target_start = timezone.make_aware(datetime.combine(day, time(10, 0)))
        source = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=source_start,
            ends_at=source_start + timedelta(hours=1),
        )
        Appointment.objects.create(
            patient=self.patient_two,
            professional=self.professional,
            starts_at=target_start,
            ends_at=target_start + timedelta(hours=1),
        )
        self.client.force_login(user)

        slots = generate_available_slots(self.professional, day, 60, exclude_appointment=source)
        target_slot = next(slot for slot in slots if slot["start_value"] == "10:00")
        self.assertEqual(target_slot["capacity"], 4)
        self.assertEqual(target_slot["remaining_capacity"], 3)
        self.assertTrue(slot_is_available(self.professional, target_start, target_start + timedelta(hours=1), source))

        response = self.client.post(
            reverse("scheduling:appointment_reschedule", args=[source.pk]),
            {
                "professional": self.professional.pk,
                "appointment_date": day.isoformat(),
                "duration_minutes": "60",
                "selected_start": "10:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        replacement = Appointment.objects.get(rescheduled_from=source)
        self.assertEqual(replacement.starts_at, target_start)
        self.assertEqual(replacement.slot_capacity, 4)

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

    def test_management_can_create_package_by_patient_and_plan(self):
        user = get_user_model().objects.create_user(username="gestao-pacote-fluido", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        patient = Patient.objects.create(full_name="Paciente Sem Plano")
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:package_create"),
            {
                "patient": patient.pk,
                "plan": self.plan.pk,
                "starts_on": timezone.localdate().isoformat(),
                "status": ServicePackage.Status.ACTIVE,
                "notes": "Adesao criada pelo fluxo simplificado.",
            },
        )

        self.assertRedirects(response, reverse("scheduling:packages"))
        membership = Membership.objects.get(patient=patient, plan=self.plan, status=Membership.Status.ACTIVE)
        package = ServicePackage.objects.get(membership=membership)
        self.assertEqual(package.total_sessions, 8)

    def test_package_form_reuses_existing_active_membership(self):
        user = get_user_model().objects.create_user(username="gestao-pacote-reuso", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:package_create"),
            {
                "patient": self.patient.pk,
                "plan": self.plan.pk,
                "starts_on": timezone.localdate().isoformat(),
                "status": ServicePackage.Status.ACTIVE,
                "notes": "",
            },
        )

        self.assertRedirects(response, reverse("scheduling:packages"))
        package = ServicePackage.objects.get(membership=self.membership)
        self.assertEqual(package.total_sessions, self.plan.default_total_sessions)
        self.assertEqual(package.membership, self.membership)

    def test_package_form_allows_different_plan_when_patient_has_active_membership(self):
        user = get_user_model().objects.create_user(username="gestao-pacote-plano-diferente", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        other_plan = ServicePlan.objects.create(
            name="Plano Diferente",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("500.00"),
            sessions_per_week=3,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:package_create"),
            {
                "patient": self.patient.pk,
                "plan": other_plan.pk,
                "starts_on": timezone.localdate().isoformat(),
                "status": ServicePackage.Status.ACTIVE,
                "notes": "",
            },
        )

        self.assertRedirects(response, reverse("scheduling:packages"))
        self.assertTrue(ServicePackage.objects.filter(membership__patient=self.patient, membership__plan=other_plan).exists())

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

    def test_availability_board_loads_and_delete_removes_rule(self):
        user = get_user_model().objects.create_user(username="gestao-disponibilidade-ui", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        availability = ProfessionalAvailability.objects.filter(professional=self.professional).first()
        self.client.force_login(user)

        response = self.client.get(reverse("scheduling:availabilities"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configure os horarios recorrentes")
        self.assertContains(response, f"{availability.session_capacity} vaga")

        delete_response = self.client.post(reverse("scheduling:availability_delete", args=[availability.pk]))
        self.assertRedirects(delete_response, reverse("scheduling:availabilities"))
        self.assertFalse(ProfessionalAvailability.objects.filter(pk=availability.pk).exists())

    def test_management_can_create_availability_batch_for_days_and_windows(self):
        user = get_user_model().objects.create_user(username="gestao-disponibilidade-lote", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        reference_date = timezone.localdate() + timedelta(days=14)
        week_start = reference_date - timedelta(days=reference_date.weekday())
        week_end = week_start + timedelta(days=6)
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:availability_create"),
            {
                "professional": self.professional.pk,
                "weekdays": ["0", "2", "4"],
                "reference_date": reference_date.isoformat(),
                "valid_scope": "week",
                "window_1_start": "08:00",
                "window_1_end": "12:00",
                "window_2_start": "14:00",
                "window_2_end": "18:00",
                "session_capacity": "6",
                "active": "on",
                "notes": "Semana experimental.",
            },
        )

        self.assertRedirects(response, reverse("scheduling:availabilities"))
        created_rules = ProfessionalAvailability.objects.filter(
            professional=self.professional,
            valid_from=week_start,
            valid_until=week_end,
            session_capacity=6,
            notes="Semana experimental.",
        )
        self.assertEqual(created_rules.count(), 6)
        self.assertEqual(set(created_rules.values_list("weekday", flat=True)), {0, 2, 4})

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
        self.assertContains(response, "Remarcacoes abertas")
        self.assertContains(response, "Avisos pendentes")
        self.assertContains(response, self.patient.full_name)
        self.assertContains(response, "data-open-appointment")
        self.assertContains(response, "agenda-action-modal")

        ics_response = self.client.get(reverse("scheduling:appointments_ical"))
        self.assertEqual(ics_response.status_code, 200)
        self.assertIn("text/calendar", ics_response["Content-Type"])
        self.assertIn("BEGIN:VCALENDAR", ics_response.content.decode())

    def test_complete_appointment_creates_attendance_record(self):
        user = get_user_model().objects.create_user(username="gestao-presenca", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        ServicePackage.objects.create(membership=self.membership, total_sessions=4, used_sessions=0)
        start = timezone.now() + timedelta(days=1)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.post(reverse("scheduling:appointment_complete", args=[appointment.pk]))

        self.assertEqual(response.status_code, 302)
        attendance = AppointmentAttendance.objects.get(appointment=appointment)
        self.assertEqual(attendance.status, AppointmentAttendance.Status.PRESENT)

    def test_management_can_mark_absence_without_consuming_credit(self):
        user = get_user_model().objects.create_user(username="gestao-falta", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        package = ServicePackage.objects.create(membership=self.membership, total_sessions=4, used_sessions=0)
        start = timezone.now() + timedelta(days=1)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:appointment_absence", args=[appointment.pk]),
            {"status": AppointmentAttendance.Status.JUSTIFIED_ABSENCE, "notes": "Avisou antes."},
        )

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        package.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.NO_SHOW)
        self.assertEqual(package.used_sessions, 0)
        self.assertEqual(appointment.attendance.status, AppointmentAttendance.Status.JUSTIFIED_ABSENCE)

    def test_patient_can_create_reschedule_request(self):
        user = get_user_model().objects.create_user(username="paciente-remarcacao", password="Senha@123")
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )
        start = timezone.now() + timedelta(days=3)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:reschedule_request_create", args=[appointment.pk]),
            {
                "preferred_date": (timezone.localdate() + timedelta(days=5)).isoformat(),
                "preferred_period": RescheduleRequest.PreferredPeriod.AFTERNOON,
                "reason": "Nao consigo chegar no horario atual.",
            },
        )

        self.assertEqual(response.status_code, 302)
        request = RescheduleRequest.objects.get(appointment=appointment)
        self.assertEqual(request.patient, self.patient)
        self.assertEqual(request.status, RescheduleRequest.Status.PENDING)

    def test_management_can_approve_reschedule_request(self):
        user = get_user_model().objects.create_user(username="gestao-aprova-remarcacao", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        start = timezone.now() + timedelta(days=3)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        request = RescheduleRequest.objects.create(
            appointment=appointment,
            patient=self.patient,
            requested_by=user,
            preferred_date=timezone.localdate() + timedelta(days=4),
            reason="Ajuste de agenda.",
        )
        self.client.force_login(user)

        response = self.client.post(reverse("scheduling:reschedule_request_decision", args=[request.pk, "aprovar"]))

        self.assertEqual(response.status_code, 302)
        request.refresh_from_db()
        self.assertEqual(request.status, RescheduleRequest.Status.APPROVED)
        self.assertEqual(request.decided_by, user)

    def test_generate_operational_notifications_creates_lesson_and_renewal_alerts(self):
        settings = ClinicSettings.load()
        settings.membership_due_reminder_days = 5
        settings.save()
        today = timezone.localdate()
        today_start = timezone.make_aware(datetime.combine(today, time(9, 0)))
        tomorrow_start = timezone.make_aware(datetime.combine(today + timedelta(days=1), time(10, 0)))
        Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=today_start,
            ends_at=today_start + timedelta(hours=1),
        )
        tomorrow_appointment = Appointment.objects.create(
            patient=self.patient_two,
            professional=self.professional,
            starts_at=tomorrow_start,
            ends_at=tomorrow_start + timedelta(hours=1),
        )
        Payment.objects.create(
            membership=self.membership,
            patient=self.patient,
            item_type=Payment.ItemType.MEMBERSHIP,
            description="Mensalidade",
            reference_month=today.replace(day=1),
            due_date=today + timedelta(days=5),
            amount=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )

        created = generate_operational_notifications(reference_date=today)

        self.assertEqual(created["appointment_day"], 1)
        self.assertEqual(created["session_confirmation"], 1)
        self.assertEqual(created["absence_warning"], 1)
        self.assertEqual(created["plan_renewal"], 1)
        self.assertTrue(
            PatientNotification.objects.filter(
                appointment=tomorrow_appointment,
                kind=PatientNotification.Kind.SESSION_CONFIRMATION,
                channel=PatientNotification.Channel.WHATSAPP,
            ).exists()
        )
        self.assertEqual(PatientNotification.objects.count(), 3)

    def test_operational_event_blocks_new_scheduled_appointments_and_creates_patient_notice(self):
        target_date = timezone.localdate() + timedelta(days=3)
        existing_start = timezone.make_aware(datetime.combine(target_date, time(11, 0)))
        appointment = Appointment.objects.create(
            patient=self.patient_two,
            professional=self.professional,
            starts_at=existing_start,
            ends_at=existing_start + timedelta(hours=1),
        )
        event = OperationalCalendarEvent.objects.create(
            event_type=OperationalCalendarEvent.EventType.HOLIDAY,
            title="Feriado municipal",
            starts_on=target_date,
            ends_on=target_date,
            message="A clinica estara fechada no feriado municipal.",
        )
        blocked_start = timezone.make_aware(datetime.combine(target_date, time(9, 0)))
        blocked_appointment = Appointment(
            patient=self.patient,
            professional=self.professional,
            starts_at=blocked_start,
            ends_at=blocked_start + timedelta(hours=1),
        )

        with self.assertRaises(ValidationError):
            blocked_appointment.full_clean()

        created = generate_operational_notifications(reference_date=timezone.localdate())

        self.assertEqual(created["operational_event"], 1)
        self.assertTrue(
            PatientNotification.objects.filter(
                appointment=appointment,
                calendar_event=event,
                kind=PatientNotification.Kind.HOLIDAY,
            ).exists()
        )

    def test_notification_preferences_prevent_financial_automations(self):
        preferences = PatientNotificationPreference.objects.create(
            patient=self.patient,
            financial_enabled=False,
        )
        today = timezone.localdate()
        settings = ClinicSettings.load()
        settings.membership_due_reminder_days = 5
        settings.save()
        Payment.objects.create(
            membership=self.membership,
            patient=self.patient,
            reference_month=today.replace(day=1),
            due_date=today + timedelta(days=5),
            amount=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )

        generate_operational_notifications(reference_date=today)

        preferences.refresh_from_db()
        self.assertFalse(PatientNotification.objects.filter(patient=self.patient, kind=PatientNotification.Kind.PLAN_RENEWAL).exists())

    def test_low_credit_alert_is_idempotent(self):
        package = ServicePackage.objects.create(
            membership=self.membership,
            total_sessions=4,
            used_sessions=3,
            starts_on=timezone.localdate(),
        )

        first = generate_operational_notifications(reference_date=timezone.localdate())
        second = generate_operational_notifications(reference_date=timezone.localdate())

        self.assertEqual(first["low_credit"], 1)
        self.assertEqual(second["low_credit"], 0)
        self.assertEqual(
            PatientNotification.objects.filter(metadata__package_id=package.pk, metadata__reason="low_credit").count(),
            1,
        )

    def test_patient_progress_page_shows_monthly_summary_goal_and_checkin(self):
        user = get_user_model().objects.create_user(username="gestao-progresso", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        start = timezone.now() - timedelta(days=1)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            status=Appointment.Status.COMPLETED,
        )
        AppointmentAttendance.objects.create(
            appointment=appointment,
            patient=self.patient,
            professional=self.professional,
            status=AppointmentAttendance.Status.PRESENT,
        )
        PatientGoal.objects.create(patient=self.patient, title="Melhorar postura", objective="Reduzir dor lombar.")
        PatientCheckIn.objects.create(patient=self.patient, feeling=PatientCheckIn.Feeling.LIGHT_PAIN, pain_level=2)
        self.client.force_login(user)

        response = self.client.get(reverse("scheduling:patient_progress", args=[self.patient.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Melhorar postura")
        self.assertContains(response, "Frequencia")


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
