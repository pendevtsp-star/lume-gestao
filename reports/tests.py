from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.models import ClinicSettings
from patients.models import Patient
from scheduling.models import Appointment, AppointmentAttendance, PatientCheckIn, PatientGoal
from team.models import Professional


class ReportsAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="gestor", password="Senha@123")
        UserProfile.objects.update_or_create(user=self.user, defaults={"role": UserProfile.Role.MANAGEMENT})

    def seed_report_data(self):
        patient = Patient.objects.create(full_name="Paciente Relatorio")
        professional = Professional.objects.create(full_name="Dra. Relatorio", specialty=Professional.Specialty.PILATES)
        plan = ServicePlan.objects.create(
            name="Plano Relatorio",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("400.00"),
            sessions_per_week=2,
        )
        membership = Membership.objects.create(patient=patient, plan=plan, due_day=10)
        Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PAID,
            paid_at=date(2026, 6, 10),
        )
        category = ExpenseCategory.objects.get(name="Aluguel")
        Expense.objects.create(
            description="Aluguel teste",
            category=category,
            kind=Expense.Kind.FIXED,
            due_date=date(2026, 6, 5),
            amount=Decimal("100.00"),
            status=Expense.Status.OPEN,
        )
        Charge.objects.create(
            patient=patient,
            description="Sessao avulsa",
            due_date=date(2026, 6, 15),
            amount=Decimal("90.00"),
            status=Charge.Status.RECEIVED,
            received_at=date(2026, 6, 15),
        )
        start = timezone.make_aware(datetime.combine(date(2026, 6, 12), time(9, 0)))
        Appointment.objects.create(
            patient=patient,
            professional=professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            status=Appointment.Status.COMPLETED,
            completed_at=start,
        )
        settings = ClinicSettings.load()
        settings.clinic_name = "Lume Relatorios"
        settings.save()

    def test_management_can_access_financial_clinic_and_audit_reports(self):
        self.seed_report_data()
        self.client.force_login(self.user)

        financial_response = self.client.get(
            reverse("reports:financial"),
            {"preset": "custom", "start": "2026-06-01", "end": "2026-06-30"},
        )
        clinic_response = self.client.get(
            reverse("reports:clinic"),
            {"preset": "custom", "start": "2026-06-01", "end": "2026-06-30"},
        )
        audit_response = self.client.get(reverse("reports:audit"))

        self.assertContains(financial_response, "Saude financeira")
        self.assertContains(financial_response, "R$ 490,00")
        self.assertContains(clinic_response, "Gestao de adesao da clinica")
        self.assertContains(clinic_response, "Dra. Relatorio")
        self.assertContains(audit_response, "ClinicSettings")

    def test_management_can_export_all_report_types(self):
        self.seed_report_data()
        self.client.force_login(self.user)

        pdf_response = self.client.get(reverse("reports:export", args=["pdf"]))
        inline_pdf_response = self.client.get(reverse("reports:financial_export", args=["pdf"]), {"inline": "1"})
        preview_response = self.client.get(reverse("reports:financial_pdf_preview"))
        xlsx_response = self.client.get(reverse("reports:export", args=["xlsx"]))
        clinic_pdf_response = self.client.get(reverse("reports:clinic_export", args=["pdf"]))
        clinic_preview_response = self.client.get(reverse("reports:clinic_pdf_preview"))
        audit_preview_response = self.client.get(reverse("reports:audit_pdf_preview"))
        audit_xlsx_response = self.client.get(reverse("reports:audit_export", args=["xlsx"]))

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertIn("attachment", pdf_response["Content-Disposition"])
        self.assertEqual(inline_pdf_response["Content-Type"], "application/pdf")
        self.assertIn("inline", inline_pdf_response["Content-Disposition"])
        self.assertContains(preview_response, "Pre-visualizar relatorio financeiro")
        self.assertContains(preview_response, "Baixar PDF")
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertEqual(
            xlsx_response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(clinic_pdf_response["Content-Type"], "application/pdf")
        self.assertContains(clinic_preview_response, "Pre-visualizar relatorio de adesao")
        self.assertContains(audit_preview_response, "Pre-visualizar relatorio de auditoria")
        self.assertEqual(
            audit_xlsx_response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_patient_cannot_access_reports(self):
        patient = Patient.objects.create(full_name="Paciente Sem Relatorio")
        user = get_user_model().objects.create_user(username="paciente-relatorio", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.PATIENT, "patient": patient})
        self.client.force_login(user)

        response = self.client.get(reverse("reports:dashboard"))

        self.assertEqual(response.status_code, 302)

    def test_monthly_report_aggregates_attendance_checkins_and_exports(self):
        self.seed_report_data()
        patient = Patient.objects.get(full_name="Paciente Relatorio")
        appointment = Appointment.objects.get(patient=patient)
        AppointmentAttendance.objects.create(appointment=appointment, patient=patient, professional=appointment.professional, status=AppointmentAttendance.Status.PRESENT)
        PatientCheckIn.objects.create(patient=patient, feeling=PatientCheckIn.Feeling.LIGHT_PAIN, pain_level=2)
        PatientGoal.objects.create(patient=patient, title="Meta mensal")
        self.client.force_login(self.user)
        params = {"preset": "custom", "start": "2026-06-01", "end": "2026-06-30"}
        response = self.client.get(reverse("reports:monthly"), params)
        export = self.client.get(reverse("reports:monthly_export", args=["xlsx"]), params)
        self.assertContains(response, "Acompanhamento mensal")
        self.assertContains(response, patient.full_name)
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
