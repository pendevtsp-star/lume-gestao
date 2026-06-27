from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.models import (
    AuditLog,
    ClinicSettings,
    GoogleCalendarIntegration,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage, ServiceUsage
from team.models import Employee, Professional


class DashboardAccessTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_authenticated_user_can_open_dashboard(self):
        user = get_user_model().objects.create_user(username="admin", password="Lume@12345")
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_dashboard_shows_weekly_birthdays_to_all_roles(self):
        today = timezone.localdate()
        birthday_patient = Patient.objects.create(
            full_name="Paciente Aniversariante",
            phone="11999990000",
            birth_date=date(1991, today.month, today.day),
        )
        linked_patient = Patient.objects.create(full_name="Paciente Usuario")
        professional = Professional.objects.create(
            full_name="Dra. Aniversario",
            specialty=Professional.Specialty.PILATES,
        )
        ProfessionalPatientAssignment.objects.create(patient=birthday_patient, professional=professional)
        roles = [
            ("gestor-aniversario", UserProfile.Role.MANAGEMENT, {}),
            ("admin-aniversario", UserProfile.Role.ADMINISTRATION, {}),
            ("prof-aniversario", UserProfile.Role.PROFESSIONAL, {"professional": professional}),
            ("paciente-aniversario", UserProfile.Role.PATIENT, {"patient": linked_patient}),
        ]

        for username, role, extra_profile_fields in roles:
            with self.subTest(role=role):
                user = get_user_model().objects.create_user(username=username, password="Lume@12345")
                UserProfile.objects.update_or_create(
                    user=user,
                    defaults={"role": role, **extra_profile_fields},
                )
                self.client.force_login(user)

                response = self.client.get(reverse("dashboard"))

                self.assertContains(response, "Aniversariantes da semana")
                self.assertContains(response, birthday_patient.full_name)
                self.assertContains(response, today.strftime("%d/%m"))
                self.assertNotContains(response, "1991")
                self.client.logout()

    def test_healthcheck_returns_runtime_status(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


class AuditLogTests(TestCase):
    def test_audit_log_is_created_when_settings_change(self):
        settings = ClinicSettings.load()
        settings.membership_due_reminder_days = 9
        settings.save()

        self.assertTrue(
            AuditLog.objects.filter(model_name="ClinicSettings", action=AuditLog.Action.UPDATED).exists()
        )


class ClinicSettingsTests(TestCase):
    def test_settings_validate_cnpj_due_day_and_business_hours(self):
        settings = ClinicSettings(cnpj="123", default_membership_due_day=31, opening_time=time(18, 0), closing_time=time(8, 0))

        with self.assertRaises(ValidationError):
            settings.full_clean()

    def test_management_can_update_clinic_settings(self):
        user = get_user_model().objects.create_user(username="gestor-config", password="Senha@123")
        UserProfile.objects.update_or_create(user=user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(user)

        response = self.client.post(
            reverse("settings"),
            {
                "clinic_name": "Lume Pilates e Fisioterapia",
                "cnpj": "12.345.678/0001-99",
                "phone": "11999990000",
                "email": "contato@lume.local",
                "address": "Rua Teste, 123",
                "business_days": "Segunda a sexta",
                "opening_time": "08:00",
                "closing_time": "18:00",
                "membership_due_reminder_days": 7,
                "default_membership_due_day": 10,
                "cancellation_deadline_hours": 24,
                "rescheduling_deadline_hours": 24,
                "cancellation_policy": "Cancelamentos sem consumo de credito.",
                "rescheduling_policy": "Reagendamentos sem consumo de credito.",
            },
        )

        self.assertEqual(response.status_code, 302)
        settings = ClinicSettings.load()
        self.assertEqual(settings.clinic_name, "Lume Pilates e Fisioterapia")
        self.assertEqual(settings.cnpj, "12345678000199")


class FunctionalRoleFlowTests(TestCase):
    def setUp(self):
        self.management = get_user_model().objects.create_user(username="gestao-fluxo", password="Senha@123")
        self.administration = get_user_model().objects.create_user(username="admin-fluxo", password="Senha@123")
        self.professional_user = get_user_model().objects.create_user(username="prof-fluxo", password="Senha@123")
        self.patient_user = get_user_model().objects.create_user(username="paciente-fluxo", password="Senha@123")

        self.patient = Patient.objects.create(full_name="Paciente Fluxo")
        self.other_patient = Patient.objects.create(full_name="Paciente Fora")
        self.professional = Professional.objects.create(
            full_name="Dra. Fluxo",
            specialty=Professional.Specialty.PHYSIOTHERAPY,
        )
        Employee.objects.create(full_name="Funcionario Fluxo", role=Employee.Role.RECEPTION)
        ProfessionalPatientAssignment.objects.create(patient=self.patient, professional=self.professional)
        ProfessionalAvailability.objects.create(
            professional=self.professional,
            weekday=0,
            starts_at=time(8, 0),
            ends_at=time(12, 0),
        )
        plan = ServicePlan.objects.create(
            name="Plano Fluxo",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("400.00"),
        )
        membership = Membership.objects.create(patient=self.patient, plan=plan, due_day=10)
        ServicePackage.objects.create(membership=membership, total_sessions=8)

        UserProfile.objects.update_or_create(user=self.management, defaults={"role": UserProfile.Role.MANAGEMENT})
        UserProfile.objects.update_or_create(
            user=self.administration,
            defaults={"role": UserProfile.Role.ADMINISTRATION},
        )
        UserProfile.objects.update_or_create(
            user=self.professional_user,
            defaults={"role": UserProfile.Role.PROFESSIONAL, "professional": self.professional},
        )
        UserProfile.objects.update_or_create(
            user=self.patient_user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )

    def assert_pages_ok(self, user, route_names):
        self.client.force_login(user)
        for route_name in route_names:
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200, route_name)

    def test_all_profiles_can_login_and_logout_with_credentials(self):
        for user in [self.management, self.administration, self.professional_user, self.patient_user]:
            self.client.logout()
            self.assertTrue(self.client.login(username=user.username, password="Senha@123"), user.username)
            response = self.client.get(reverse("dashboard"))
            self.assertEqual(response.status_code, 200, user.username)
            logout_response = self.client.post(reverse("logout"))
            self.assertEqual(logout_response.status_code, 302, user.username)

    def test_management_can_open_full_backoffice_flow(self):
        self.assert_pages_ok(
            self.management,
            [
                "dashboard",
                "patients:list",
                "scheduling:appointments",
                "scheduling:availabilities",
                "reports:dashboard",
                "reports:financial",
                "reports:clinic",
                "billing:memberships",
                "billing:payments",
                "billing:charges",
                "billing:expenses",
                "scheduling:packages",
                "billing:plans",
                "patients:assignments",
                "team:professionals",
                "team:employees",
                "accounts:list",
                "audit",
                "settings",
                "integrations",
            ],
        )

    def test_management_review_covers_exports_expenses_and_audit(self):
        category = ExpenseCategory.objects.get(name="Aluguel")
        Expense.objects.create(
            description="Energia funcional",
            category=category,
            kind=Expense.Kind.FIXED,
            due_date=date(2026, 6, 5),
            amount=Decimal("300.00"),
            status=Expense.Status.OPEN,
        )
        self.client.force_login(self.management)

        expense_response = self.client.get(reverse("billing:expenses"))
        pdf_response = self.client.get(reverse("reports:export", args=["pdf"]))
        xlsx_response = self.client.get(reverse("reports:export", args=["xlsx"]))
        clinic_export_response = self.client.get(reverse("reports:clinic_export", args=["pdf"]))
        ics_response = self.client.get(reverse("scheduling:appointments_ical"))
        settings_response = self.client.post(
            reverse("settings"),
            {
                "clinic_name": "Lume Revisao",
                "cnpj": "",
                "phone": "",
                "email": "",
                "address": "",
                "business_days": "Segunda a sexta",
                "opening_time": "08:00",
                "closing_time": "18:00",
                "membership_due_reminder_days": 6,
                "default_membership_due_day": 10,
                "cancellation_deadline_hours": 24,
                "rescheduling_deadline_hours": 24,
                "cancellation_policy": "",
                "rescheduling_policy": "",
            },
        )
        audit_response = self.client.get(reverse("audit"))

        self.assertContains(expense_response, "Energia funcional")
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertEqual(
            xlsx_response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(clinic_export_response["Content-Type"], "application/pdf")
        self.assertIn("text/calendar", ics_response["Content-Type"])
        self.assertEqual(settings_response.status_code, 302)
        self.assertContains(audit_response, "ClinicSettings")

    def test_administration_can_open_operational_finance_but_not_management_only_pages(self):
        self.assert_pages_ok(
            self.administration,
            [
                "dashboard",
                "patients:list",
                "scheduling:appointments",
                "scheduling:availabilities",
                "reports:dashboard",
                "reports:financial",
                "reports:clinic",
                "billing:memberships",
                "billing:payments",
                "billing:expenses",
                "patients:assignments",
                "team:professionals",
            ],
        )
        for route_name in ["accounts:list", "audit", "settings"]:
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 302, route_name)

    def test_professional_flow_is_scoped_to_assigned_patients(self):
        self.client.force_login(self.professional_user)

        patients_response = self.client.get(reverse("patients:list"))
        notes_response = self.client.get(reverse("patients:notes"))
        finance_response = self.client.get(reverse("billing:payments"))

        self.assertContains(patients_response, self.patient.full_name)
        self.assertNotContains(patients_response, self.other_patient.full_name)
        self.assertContains(notes_response, self.patient.full_name)
        self.assertEqual(finance_response.status_code, 302)

    def test_patient_flow_is_scoped_to_self_and_blocks_backoffice(self):
        self.client.force_login(self.patient_user)

        patients_response = self.client.get(reverse("patients:list"))
        reports_response = self.client.get(reverse("reports:dashboard"))
        audit_response = self.client.get(reverse("audit"))

        self.assertContains(patients_response, self.patient.full_name)
        self.assertNotContains(patients_response, self.other_patient.full_name)
        self.assertEqual(reports_response.status_code, 302)
        self.assertEqual(audit_response.status_code, 302)

    def test_patient_dashboard_shows_plan_payment_and_credit_summary(self):
        membership = Membership.objects.get(patient=self.patient)
        Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 10),
            amount=Decimal("400.00"),
            status=Payment.Status.PENDING,
        )
        starts_at = timezone.make_aware(datetime.combine(timezone.localdate(), time(9, 0))) - timedelta(days=1)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            status=Appointment.Status.COMPLETED,
        )
        package = ServicePackage.objects.get(membership=membership)
        ServiceUsage.objects.create(service_package=package, appointment=appointment, units=1)
        package.used_sessions = 1
        package.save()
        self.client.force_login(self.patient_user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Meu plano")
        self.assertContains(response, "Plano Fluxo")
        self.assertContains(response, "Proximo pagamento")
        self.assertContains(response, "Pacote atual")


class IntegrationsTests(TestCase):
    def setUp(self):
        self.management = get_user_model().objects.create_user(username="gestor-integracoes", password="Senha@123")
        self.administration = get_user_model().objects.create_user(username="admin-integracoes", password="Senha@123")
        self.patient_user = get_user_model().objects.create_user(username="paciente-integracoes", password="Senha@123")
        self.patient = Patient.objects.create(full_name="Paciente Integracoes", phone="11999990000", birth_date=date(1990, 5, 2))
        self.professional = Professional.objects.create(
            full_name="Dra. Integracoes",
            specialty=Professional.Specialty.PILATES,
        )
        ProfessionalPatientAssignment.objects.create(patient=self.patient, professional=self.professional)
        self.plan = ServicePlan.objects.create(
            name="Plano Integracoes",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("320.00"),
        )
        self.membership = Membership.objects.create(patient=self.patient, plan=self.plan, due_day=10)
        self.payment = Payment.objects.create(
            membership=self.membership,
            reference_month=date(2026, 6, 1),
            due_date=date(2026, 6, 30),
            amount=Decimal("320.00"),
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=timezone.now() + timedelta(days=2),
            ends_at=timezone.now() + timedelta(days=2, hours=1),
        )
        UserProfile.objects.update_or_create(user=self.management, defaults={"role": UserProfile.Role.MANAGEMENT})
        UserProfile.objects.update_or_create(
            user=self.administration,
            defaults={"role": UserProfile.Role.ADMINISTRATION},
        )
        UserProfile.objects.update_or_create(
            user=self.patient_user,
            defaults={"role": UserProfile.Role.PATIENT, "patient": self.patient},
        )

    def test_management_can_open_integrations(self):
        self.client.force_login(self.management)

        response = self.client.get(reverse("integrations"))

        self.assertContains(response, "Google Agenda")
        self.assertContains(response, "ZapFisio")

    def test_administration_can_open_integrations(self):
        self.client.force_login(self.administration)

        response = self.client.get(reverse("integrations"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conexoes")

    def test_patient_cannot_open_integrations(self):
        self.client.force_login(self.patient_user)

        response = self.client.get(reverse("integrations"))

        self.assertEqual(response.status_code, 302)

    def test_whatsapp_dry_run_test_updates_status(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"enabled": True, "dry_run": True, "phone_number_id": "123", "clinic_whatsapp_number": "5511999990000"},
        )

        response = self.client.post(
            reverse("integrations"),
            {
                "action": "test_whatsapp",
                "test_number": "11999990000",
                "test_message": "Teste Lume",
            },
        )

        self.assertEqual(response.status_code, 302)
        integration = WhatsAppIntegration.load()
        self.assertIsNotNone(integration.last_test_at)
        self.assertEqual(integration.last_error, "")

    def test_management_can_save_whatsapp_message_template(self):
        self.client.force_login(self.management)
        template = WhatsAppMessageTemplate.ensure_defaults()[0]

        response = self.client.post(
            reverse("integrations"),
            {
                "action": f"save_template:{template.template_type}",
                "tab": "messages",
                f"template-{template.template_type}-active": "on",
                f"template-{template.template_type}-title": "Lembrete VIP",
                f"template-{template.template_type}-description": "Mensagem refinada",
                f"template-{template.template_type}-body": "Oi [Paciente], confirme [Data] as [Horario].",
                f"template-{template.template_type}-send_time": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        template.refresh_from_db()
        self.assertEqual(template.title, "Lembrete VIP")
        self.assertEqual(template.updated_by, self.management)

    def test_management_can_send_whatsapp_template_and_log_it(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"enabled": True, "dry_run": True, "phone_number_id": "123", "clinic_whatsapp_number": "5511999990000"},
        )
        WhatsAppMessageTemplate.ensure_defaults()
        template = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT
        )

        response = self.client.post(
            reverse("integrations"),
            {
                "action": "send_template:appointment",
                "tab": "messages",
                "send-appointment-appointment": self.appointment.pk,
                "send-appointment-custom_number": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        log = WhatsAppMessageLog.objects.get(template=template)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.DRY_RUN)
        self.assertEqual(log.patient, self.patient)
        self.assertIn(self.patient.full_name, log.rendered_message)

    def test_management_can_send_birthday_message_from_dashboard(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"enabled": True, "dry_run": True, "phone_number_id": "123", "clinic_whatsapp_number": "5511999990000"},
        )
        WhatsAppMessageTemplate.ensure_defaults()
        template = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.BIRTHDAY
        )

        response = self.client.post(reverse("birthday_whatsapp_send", args=[self.patient.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("dashboard"))
        log = WhatsAppMessageLog.objects.get(template=template)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.DRY_RUN)
        self.assertEqual(log.patient, self.patient)
        self.assertIn(self.patient.full_name, log.rendered_message)

    def test_management_can_schedule_whatsapp_template(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"enabled": True, "dry_run": True, "phone_number_id": "123", "clinic_whatsapp_number": "5511999990000"},
        )
        WhatsAppMessageTemplate.ensure_defaults()
        scheduled_for = (timezone.now() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")

        response = self.client.post(
            reverse("integrations"),
            {
                "action": "send_template:appointment",
                "tab": "messages",
                "send-appointment-appointment": self.appointment.pk,
                "send-appointment-custom_number": "",
                "send-appointment-send_mode": "schedule",
                "send-appointment-scheduled_for": scheduled_for,
            },
        )

        self.assertEqual(response.status_code, 302)
        log = WhatsAppMessageLog.objects.get(status=WhatsAppMessageLog.Status.SCHEDULED)
        self.assertEqual(log.patient, self.patient)
        self.assertIsNotNone(log.scheduled_for)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_whatsapp_queue_command_processes_scheduled_messages(self, send_mock):
        send_mock.return_value = {"dry_run": True, "to": "5511999990000", "message": "Oi"}
        integration = WhatsAppIntegration.load()
        integration.enabled = True
        integration.dry_run = True
        integration.clinic_whatsapp_number = "5511999990000"
        integration.save()
        template = WhatsAppMessageTemplate.ensure_defaults()[0]
        WhatsAppMessageLog.objects.create(
            integration=integration,
            template=template,
            patient=self.patient,
            recipient_name=self.patient.full_name,
            recipient_number="5511999990000",
            rendered_message="Oi",
            status=WhatsAppMessageLog.Status.SCHEDULED,
            scheduled_for=timezone.now() - timedelta(minutes=5),
        )

        call_command("process_whatsapp_queue", limit=10)

        log = WhatsAppMessageLog.objects.get(template=template)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.DRY_RUN)
        self.assertIsNotNone(log.sent_at)

    def test_management_can_cancel_scheduled_message(self):
        self.client.force_login(self.management)
        integration = WhatsAppIntegration.load()
        template = WhatsAppMessageTemplate.ensure_defaults()[0]
        log = WhatsAppMessageLog.objects.create(
            integration=integration,
            template=template,
            patient=self.patient,
            recipient_name=self.patient.full_name,
            recipient_number="5511999990000",
            rendered_message="Oi",
            status=WhatsAppMessageLog.Status.SCHEDULED,
            scheduled_for=timezone.now() + timedelta(hours=2),
        )

        response = self.client.post(
            reverse("integrations"),
            {
                "action": f"cancel_scheduled:{log.pk}",
                "tab": "messages",
            },
        )

        self.assertEqual(response.status_code, 302)
        log.refresh_from_db()
        self.assertEqual(log.status, WhatsAppMessageLog.Status.CANCELED)

    @override_settings(
        GOOGLE_CALENDAR_CLIENT_ID="client-id",
        GOOGLE_CALENDAR_CLIENT_SECRET="client-secret",
    )
    def test_google_connect_redirects_to_oauth(self):
        self.client.force_login(self.management)

        response = self.client.get(reverse("integrations_google_connect"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com", response["Location"])


class GoogleCalendarSignalTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(full_name="Paciente Google", phone="11999990000")
        self.professional = Professional.objects.create(
            full_name="Dra. Agenda Google",
            specialty=Professional.Specialty.PILATES,
        )
        ProfessionalPatientAssignment.objects.create(patient=self.patient, professional=self.professional)
        self.integration = GoogleCalendarIntegration.load()
        self.integration.enabled = True
        self.integration.sync_on_save = True
        self.integration.connected_email = "clinica@lume.local"
        self.integration.refresh_token = "refresh-token"
        self.integration.access_token = "access-token"
        self.integration.token_expires_at = timezone.now() + timedelta(hours=2)
        self.integration.save()

    @override_settings(GOOGLE_CALENDAR_SYNC_ENABLED=True)
    @patch("core.signals.sync_appointment_to_google")
    def test_appointment_create_triggers_google_sync(self, sync_mock):
        with self.captureOnCommitCallbacks(execute=True):
            appointment = Appointment.objects.create(
                patient=self.patient,
                professional=self.professional,
                starts_at=timezone.now() + timedelta(days=2),
                ends_at=timezone.now() + timedelta(days=2, hours=1),
            )

        self.assertTrue(sync_mock.called)
        synced_appointment = sync_mock.call_args[0][0]
        self.assertEqual(synced_appointment.pk, appointment.pk)

    @override_settings(GOOGLE_CALENDAR_SYNC_ENABLED=True)
    @patch("core.signals.delete_google_event")
    def test_appointment_delete_removes_google_event(self, delete_mock):
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=timezone.now() + timedelta(days=3),
            ends_at=timezone.now() + timedelta(days=3, hours=1),
            external_provider="google",
            external_event_id="google-event-123",
        )

        with self.captureOnCommitCallbacks(execute=True):
            appointment.delete()

        delete_mock.assert_called_once_with("google-event-123", integration=self.integration)
