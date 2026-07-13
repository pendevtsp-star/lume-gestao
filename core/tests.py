from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Charge, Expense, ExpenseCategory, Membership, Payment, ServicePlan
from core.models import (
    AuditLog,
    ClinicSettings,
    GoogleCalendarIntegration,
    WhatsAppAutomationSettings,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from core.services.whatsapp_automation import enqueue_automatic_whatsapp_messages
from patients.models import Patient, ProfessionalPatientAssignment
from scheduling.models import Appointment, PatientNotification, ProfessionalAvailability, ServicePackage, ServiceUsage
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

    def test_dashboard_financial_notification_uses_existing_payment_route(self):
        user = get_user_model().objects.create_superuser(username="gestor-financeiro", password="Lume@12345")
        patient = Patient.objects.create(full_name="Paciente com pendencia")
        Charge.objects.create(
            patient=patient,
            description="Mensalidade vencida",
            due_date=timezone.localdate() - timedelta(days=1),
            amount=Decimal("120.00"),
            status=Charge.Status.OVERDUE,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{reverse('billing:payments')}?q=overdue")

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
        self.assertEqual(response.json(), {"status": "ok"})

    def test_healthz_is_public_and_does_not_expose_runtime_details(self):
        response = self.client.get("/healthz/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertNotIn("database_engine", response.json())
        self.assertNotIn("environment", response.json())


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


@override_settings(SECURE_SSL_REDIRECT=False)
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

    def test_management_can_open_integration_tabs(self):
        self.client.force_login(self.management)

        for tab in ["connections", "messages"]:
            with self.subTest(tab=tab):
                response = self.client.get(f"{reverse('integrations')}?tab={tab}")

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Integracoes")

    def test_connections_tab_prioritizes_qr_flow_when_meta_credentials_exist(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": True,
                "clinic_whatsapp_number": "11999990000",
                "embedded_app_id": "123456",
                "embedded_config_id": "config-123",
                "embedded_app_secret": "secret-123",
            },
        )

        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertContains(response, "Como conectar")
        self.assertNotContains(response, "Conectar WhatsApp oficial")

    def test_management_can_select_whatsapp_web_gateway_mode(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "provider": WhatsAppIntegration.Provider.META,
                "enabled": False,
                "dry_run": False,
                "clinic_whatsapp_number": "82993453535",
            },
        )

        response = self.client.post(
            reverse("integrations"),
            {"action": "select_whatsapp_web_gateway", "tab": "connections"},
        )

        self.assertEqual(response.status_code, 302)
        integration = WhatsAppIntegration.load()
        self.assertEqual(integration.provider, WhatsAppIntegration.Provider.WEB_GATEWAY)
        self.assertTrue(integration.enabled)
        self.assertEqual(integration.clinic_whatsapp_number, "82993453535")

    def test_connections_tab_shows_disconnect_whatsapp_when_connected(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": True,
                "clinic_whatsapp_number": "11999990000",
                "phone_number_id": "123456",
            },
        )

        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertContains(response, "Desconectar WhatsApp")

    @override_settings(
        WHATSAPP_EMBEDDED_APP_ID="meta-app-id-real-fake",
        WHATSAPP_EMBEDDED_CONFIG_ID="meta-config-real-fake",
        WHATSAPP_EMBEDDED_APP_SECRET="meta-app-secret-real-fake",
    )
    def test_connections_tab_shows_whatsapp_runtime_status(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": True,
                "clinic_whatsapp_number": "11999990000",
                "phone_number_id": "123456",
            },
        )

        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertContains(response, "Como conectar")
        self.assertContains(response, "Sessao pareada")
        self.assertNotContains(response, "Diagnostico tecnico da conexao Meta")

    @override_settings(WHATSAPP_WEB_GATEWAY_URL="http://gateway.local", WHATSAPP_DRY_RUN=False)
    @patch("core.views.whatsapp_web_gateway_status")
    def test_connections_tab_shows_web_gateway_whatsapp_mode(self, gateway_status):
        gateway_status.return_value = {"ok": True, "ready": False, "hasQr": True}
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "provider": WhatsAppIntegration.Provider.WEB_GATEWAY,
                "enabled": True,
                "dry_run": False,
                "clinic_whatsapp_number": "5511999990000",
            },
        )

        integration = WhatsAppIntegration.load()
        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertTrue(integration.is_connected)
        self.assertContains(response, "WhatsApp Web")
        self.assertContains(response, "Ver mensagens e automacoes")
        self.assertContains(response, "Escaneie o QR")

    def test_management_can_disconnect_whatsapp(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": True,
                "clinic_whatsapp_number": "11999990000",
                "phone_number_id": "123456",
                "access_token": "token-real-falso",
                "connected_at": timezone.now(),
            },
        )

        response = self.client.post(reverse("integrations"), {"action": "disconnect_whatsapp", "tab": "connections"})

        self.assertEqual(response.status_code, 302)
        integration = WhatsAppIntegration.load()
        self.assertFalse(integration.enabled)
        self.assertFalse(integration.access_token)
        self.assertIsNone(integration.connected_at)

    @override_settings(WHATSAPP_META_PHONE_NUMBER_ID="cole-o-phone-number-id", WHATSAPP_META_ACCESS_TOKEN="cole-o-token")
    def test_whatsapp_number_only_does_not_count_as_connected(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": True,
                "clinic_whatsapp_number": "11999990000",
            },
        )

        integration = WhatsAppIntegration.load()
        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertFalse(integration.is_connected)
        self.assertContains(response, "Status do WhatsApp Web")

    @override_settings(
        WHATSAPP_EMBEDDED_APP_ID="env-app-id",
        WHATSAPP_EMBEDDED_CONFIG_ID="env-config-id",
        WHATSAPP_EMBEDDED_APP_SECRET="env-secret",
    )
    def test_connections_tab_uses_meta_embedded_signup_from_env(self):
        self.client.force_login(self.management)

        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertContains(response, "Status do WhatsApp Web")
        self.assertNotContains(response, "Aguardando conexao Meta")

    @override_settings(
        WHATSAPP_EMBEDDED_APP_ID="env-app-id",
        WHATSAPP_EMBEDDED_CONFIG_ID="env-config-id",
        WHATSAPP_EMBEDDED_APP_SECRET="env-secret",
    )
    def test_connections_tab_translates_common_meta_errors_to_friendly_guidance(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": False,
                "phone_number_id": "628901596970173",
                "clinic_whatsapp_number": "5582993453535",
                "last_error": 'HTTP 400: {"error":{"message":"(#133010) Account not registered"}}',
            },
        )

        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertContains(response, "Status do WhatsApp Web")
        self.assertNotContains(response, "A Meta ainda nao liberou esse numero para envio real.")

    @override_settings(PUBLIC_BASE_URL="https://sistema.clinicafisiolume.com.br")
    def test_connections_tab_shows_public_google_callback(self):
        self.client.force_login(self.management)

        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertContains(
            response,
            "https://sistema.clinicafisiolume.com.br/integracoes/google/callback/",
        )

    @override_settings(PUBLIC_BASE_URL="https://sistema.clinicafisiolume.com.br")
    def test_management_can_generate_and_revoke_secure_google_ics_link(self):
        self.client.force_login(self.management)

        response = self.client.post(reverse("integrations"), {"action": "regenerate_google_ics", "tab": "connections"})

        self.assertEqual(response.status_code, 302)
        integration = GoogleCalendarIntegration.load()
        self.assertTrue(integration.has_calendar_feed)
        self.assertGreater(len(integration.calendar_feed_token), 40)

        feed_response = self.client.get(reverse("integrations_google_ics_feed", args=[integration.calendar_feed_token]))
        body = feed_response.content.decode()
        self.assertEqual(feed_response.status_code, 200)
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertNotIn(self.patient.full_name, body)

        response = self.client.post(reverse("integrations"), {"action": "revoke_google_ics", "tab": "connections"})
        self.assertEqual(response.status_code, 302)
        integration.refresh_from_db()
        self.assertFalse(integration.has_calendar_feed)

    def test_google_ics_feed_rejects_invalid_token(self):
        response = self.client.get(reverse("integrations_google_ics_feed", args=["token-invalido"]))

        self.assertEqual(response.status_code, 404)

    @override_settings(
        GOOGLE_CALENDAR_CLIENT_ID="cole-o-client-id-google",
        GOOGLE_CALENDAR_CLIENT_SECRET="cole-o-client-secret-google",
        WHATSAPP_EMBEDDED_APP_ID="cole-o-meta-app-id",
        WHATSAPP_EMBEDDED_CONFIG_ID="cole-o-meta-configuration-id",
        WHATSAPP_EMBEDDED_APP_SECRET="cole-o-meta-app-secret",
    )
    def test_placeholder_credentials_do_not_enable_connection_buttons(self):
        self.client.force_login(self.management)

        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertContains(response, "Configurar credenciais")
        self.assertContains(response, "Status do WhatsApp Web")
        self.assertContains(response, "Conectar com Google")
        self.assertNotContains(response, "Conectar WhatsApp oficial")

    @override_settings(
        GOOGLE_CALENDAR_CLIENT_ID="cole-o-client-id-google",
        GOOGLE_CALENDAR_CLIENT_SECRET="cole-o-client-secret-google",
    )
    def test_check_google_calendar_setup_rejects_placeholder_credentials(self):
        with self.assertRaises(CommandError):
            call_command("check_google_calendar_setup")

    @override_settings(
        GOOGLE_CALENDAR_CLIENT_ID="google-client-id-real-fake",
        GOOGLE_CALENDAR_CLIENT_SECRET="google-client-secret-real-fake",
        PUBLIC_BASE_URL="https://sistema.clinicafisiolume.com.br",
    )
    def test_check_google_calendar_setup_reports_ready_credentials(self):
        output = StringIO()

        call_command("check_google_calendar_setup", stdout=output)

        self.assertIn("Credenciais prontas", output.getvalue())

    @override_settings(
        WHATSAPP_EMBEDDED_APP_ID="meta-app-id-real-fake",
        WHATSAPP_EMBEDDED_CONFIG_ID="meta-config-real-fake",
        WHATSAPP_EMBEDDED_APP_SECRET="meta-app-secret-real-fake",
    )
    def test_check_whatsapp_setup_reports_embedded_signup(self):
        output = StringIO()

        call_command("check_whatsapp_setup", stdout=output)

        self.assertIn("Embedded Signup: sim", output.getvalue())

    @patch("core.views.subscribe_whatsapp_business_account")
    @patch("core.views.connect_whatsapp_embedded_signup")
    def test_management_can_finish_whatsapp_embedded_signup(self, connect_mock, subscribe_mock):
        self.client.force_login(self.management)
        connect_mock.return_value = {"access_token": "token"}
        subscribe_mock.return_value = {"success": True}

        response = self.client.post(
            reverse("integrations"),
            {
                "action": "finish_whatsapp_embedded",
                "embedded_code": "oauth-code",
                "embedded_phone_number_id": "phone-123",
                "embedded_business_account_id": "waba-123",
                "embedded_clinic_number": "5511999990000",
            },
        )

        self.assertEqual(response.status_code, 302)
        integration = WhatsAppIntegration.load()
        self.assertEqual(integration.phone_number_id, "phone-123")
        self.assertEqual(integration.business_account_id, "waba-123")
        self.assertEqual(integration.clinic_whatsapp_number, "5511999990000")
        connect_mock.assert_called_once()
        subscribe_mock.assert_called_once()

    @patch("core.views.subscribe_whatsapp_business_account")
    @patch("core.views.connect_whatsapp_embedded_signup")
    def test_management_can_finish_whatsapp_embedded_signup_with_browser_token(self, connect_mock, subscribe_mock):
        self.client.force_login(self.management)
        connect_mock.return_value = {"access_token": "browser-token", "source": "browser_auth_response"}
        subscribe_mock.return_value = {"success": True}

        response = self.client.post(
            reverse("integrations"),
            {
                "action": "finish_whatsapp_embedded",
                "embedded_access_token": "browser-token",
                "embedded_phone_number_id": "phone-123",
                "embedded_business_account_id": "waba-123",
                "embedded_clinic_number": "5511999990000",
            },
        )

        self.assertEqual(response.status_code, 302)
        connect_mock.assert_called_once()
        self.assertEqual(connect_mock.call_args.kwargs["browser_access_token"], "browser-token")
        subscribe_mock.assert_called_once()

    def test_messages_tab_filters_single_template(self):
        self.client.force_login(self.management)

        response = self.client.get(f"{reverse('integrations')}?tab=messages&message=charge")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mensagem de Cobranca")
        self.assertContains(response, 'value="send_template:charge"')
        self.assertNotContains(response, 'value="send_template:appointment"')
        self.assertNotContains(response, 'value="send_template:birthday"')

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

    @override_settings(WHATSAPP_DRY_RUN=False)
    @patch("core.views.send_whatsapp_text")
    def test_whatsapp_live_test_requires_confirmation(self, send_mock):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": False,
                "phone_number_id": "123",
                "access_token": "token-real-falso",
                "clinic_whatsapp_number": "5511999990000",
            },
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
        send_mock.assert_not_called()

    @override_settings(WHATSAPP_DRY_RUN=False)
    @patch("core.views.send_whatsapp_text")
    def test_whatsapp_live_test_runs_with_confirmation(self, send_mock):
        self.client.force_login(self.management)
        send_mock.return_value = {"messages": [{"id": "wa-1"}], "to": "5511999990000"}
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": False,
                "phone_number_id": "123",
                "access_token": "token-real-falso",
                "clinic_whatsapp_number": "5511999990000",
            },
        )

        response = self.client.post(
            reverse("integrations"),
            {
                "action": "test_whatsapp",
                "test_number": "11999990000",
                "test_message": "Teste Lume",
                "confirm_live_test": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        send_mock.assert_called_once()

    @override_settings(WHATSAPP_DRY_RUN=False)
    def test_send_test_whatsapp_blocks_live_without_explicit_flag(self):
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": False,
                "phone_number_id": "123",
                "access_token": "token-real-falso",
                "clinic_whatsapp_number": "5511999990000",
            },
        )

        with self.assertRaises(CommandError):
            call_command("send_test_whatsapp", "11999990000")

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

    @override_settings(WHATSAPP_WEB_GATEWAY_URL="http://gateway.local", WHATSAPP_DRY_RUN=False)
    @patch("core.views.send_whatsapp_text")
    def test_management_can_send_web_gateway_whatsapp_template(self, send_whatsapp_text_mock):
        send_whatsapp_text_mock.return_value = {
            "ok": True,
            "provider": "whatsapp_web",
            "to": "5511999990000",
            "messageId": "web-msg-1",
        }
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "provider": WhatsAppIntegration.Provider.WEB_GATEWAY,
                "enabled": True,
                "dry_run": False,
                "clinic_whatsapp_number": "5511999990000",
            },
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
        self.assertEqual(log.status, WhatsAppMessageLog.Status.SENT)
        self.assertEqual(log.patient, self.patient)
        self.assertEqual(log.provider_reference, "web-msg-1")
        send_whatsapp_text_mock.assert_called_once()

    def test_management_can_save_whatsapp_automation_settings(self):
        self.client.force_login(self.management)

        response = self.client.post(
            reverse("integrations"),
            {
                "action": "save_automation",
                "tab": "messages",
                "message": "appointment",
                "automation-appointment_reminders_enabled": "on",
                "automation-appointment_reminder_hours_before": 12,
                "automation-birthday_messages_enabled": "on",
                "automation-birthday_send_time": "07:30",
                "automation-membership_due_reminders_enabled": "on",
                "automation-membership_due_days_before": 3,
                "automation-membership_due_on_date": "on",
                "automation-membership_overdue_enabled": "on",
                "automation-membership_overdue_days_after": 1,
                "automation-charge_overdue_enabled": "on",
                "automation-charge_overdue_days_after": 1,
            },
        )

        self.assertEqual(response.status_code, 302)
        automation = WhatsAppAutomationSettings.load()
        self.assertTrue(automation.appointment_reminders_enabled)
        self.assertEqual(automation.appointment_reminder_hours_before, 12)
        self.assertTrue(automation.birthday_messages_enabled)
        self.assertEqual(automation.birthday_send_time, time(7, 30))

    def test_whatsapp_queue_command_creates_automatic_appointment_reminder(self):
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"enabled": True, "dry_run": True, "phone_number_id": "123", "clinic_whatsapp_number": "5511999990000"},
        )
        WhatsAppMessageTemplate.ensure_defaults()
        start = timezone.now() + timedelta(hours=24, minutes=10)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            status=Appointment.Status.SCHEDULED,
        )

        call_command("process_whatsapp_queue", limit=10, verbosity=0)

        log = WhatsAppMessageLog.objects.get(appointment=appointment)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.DRY_RUN)
        self.assertIn(self.patient.full_name, log.rendered_message)
        notification = PatientNotification.objects.get(appointment=appointment)
        self.assertEqual(notification.kind, PatientNotification.Kind.SESSION_CONFIRMATION)
        self.assertEqual(notification.channel, PatientNotification.Channel.WHATSAPP)
        self.assertEqual(notification.status, PatientNotification.Status.SENT)
        self.assertEqual(notification.attempts, 1)

    def test_whatsapp_queue_creates_a_same_day_reminder_without_repeating_confirmation(self):
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"enabled": True, "dry_run": True, "phone_number_id": "123", "clinic_whatsapp_number": "5511999990000"},
        )
        automation = WhatsAppAutomationSettings.load()
        automation.appointment_reminder_hours_before = 24
        automation.appointment_day_reminders_enabled = True
        automation.appointment_day_reminder_hours_before = 3
        automation.save()
        start = timezone.now() + timedelta(hours=3, minutes=10)
        appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            status=Appointment.Status.SCHEDULED,
        )

        call_command("process_whatsapp_queue", limit=10, verbosity=0)
        call_command("process_whatsapp_queue", limit=10, verbosity=0)

        self.assertEqual(
            WhatsAppMessageLog.objects.filter(automation_key=f"appointment-day:{appointment.pk}").count(),
            1,
        )
        notification = PatientNotification.objects.get(
            appointment=appointment,
            kind=PatientNotification.Kind.APPOINTMENT_DAY,
        )
        self.assertEqual(notification.status, PatientNotification.Status.SENT)
        self.assertEqual(notification.attempts, 1)

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

    def test_google_connect_uses_saved_oauth_credentials(self):
        self.client.force_login(self.management)
        integration = GoogleCalendarIntegration.load()
        integration.oauth_client_id = "saved-client-id"
        integration.oauth_client_secret = "saved-client-secret"
        integration.save()

        response = self.client.get(reverse("integrations_google_connect"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com", response["Location"])
        self.assertIn("client_id=saved-client-id", response["Location"])

    def test_management_can_disconnect_google_calendar(self):
        self.client.force_login(self.management)
        integration = GoogleCalendarIntegration.load()
        integration.enabled = True
        integration.connected_email = "clinica@lume.local"
        integration.refresh_token = "refresh-token"
        integration.access_token = "access-token"
        integration.token_expires_at = timezone.now() + timedelta(hours=1)
        integration.save()

        response = self.client.post(
            reverse("integrations"),
            {
                "action": "disconnect_google",
                "tab": "connections",
            },
        )

        self.assertEqual(response.status_code, 302)
        integration.refresh_from_db()
        self.assertFalse(integration.enabled)
        self.assertEqual(integration.connected_email, "")
        self.assertEqual(integration.refresh_token, "")
        self.assertEqual(integration.access_token, "")
        self.assertIsNone(integration.token_expires_at)

    def test_secret_fields_are_not_rendered_back_to_browser(self):
        self.client.force_login(self.management)
        GoogleCalendarIntegration.objects.update_or_create(
            pk=1,
            defaults={"oauth_client_id": "client-id", "oauth_client_secret": "super-secret-google"},
        )
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"embedded_app_id": "app-id", "embedded_config_id": "config-id", "embedded_app_secret": "super-secret-meta"},
        )

        response = self.client.get(f"{reverse('integrations')}?tab=connections")

        self.assertNotContains(response, "super-secret-google")
        self.assertNotContains(response, "super-secret-meta")

    @override_settings(WHATSAPP_DRY_RUN=False)
    def test_real_whatsapp_send_requires_meta_template_name(self):
        self.client.force_login(self.management)
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "dry_run": False,
                "phone_number_id": "phone-id",
                "access_token": "access-token",
                "clinic_whatsapp_number": "5511999990000",
            },
        )
        WhatsAppMessageTemplate.ensure_defaults()

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
        log = WhatsAppMessageLog.objects.get(template__template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.FAILED)
        self.assertIn("Template nao configurado", log.error_message)

    def test_financial_whatsapp_automation_schedules_due_and_overdue_messages(self):
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"enabled": True, "dry_run": True, "phone_number_id": "123", "clinic_whatsapp_number": "5511999990000"},
        )
        WhatsAppMessageTemplate.ensure_defaults()
        automation = WhatsAppAutomationSettings.load()
        automation.membership_due_reminders_enabled = True
        automation.membership_due_days_before = 3
        automation.membership_due_on_date = False
        automation.membership_overdue_enabled = True
        automation.membership_overdue_days_after = 1
        automation.charge_overdue_enabled = True
        automation.charge_overdue_days_after = 1
        automation.save()
        now = timezone.make_aware(datetime(2026, 6, 27, 9, 0))
        self.payment.due_date = date(2026, 6, 30)
        self.payment.save(update_fields=["due_date"])
        overdue_payment = Payment.objects.create(
            membership=self.membership,
            reference_month=date(2026, 7, 1),
            due_date=date(2026, 6, 26),
            amount=Decimal("320.00"),
            status=Payment.Status.OVERDUE,
        )
        charge = Charge.objects.create(
            patient=self.patient,
            description="Cobranca teste",
            due_date=date(2026, 6, 26),
            amount=Decimal("90.00"),
            status=Charge.Status.OVERDUE,
        )

        created = enqueue_automatic_whatsapp_messages(now=now)

        self.assertEqual(created["membership_due"], 1)
        self.assertEqual(created["membership_overdue"], 1)
        self.assertEqual(created["charge_overdue"], 1)
        self.assertTrue(WhatsAppMessageLog.objects.filter(payment=self.payment).exists())
        self.assertTrue(WhatsAppMessageLog.objects.filter(payment=overdue_payment).exists())
        self.assertTrue(WhatsAppMessageLog.objects.filter(charge=charge).exists())


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
