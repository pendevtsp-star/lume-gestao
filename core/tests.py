from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import AuditLog, ClinicSettings


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


class AuditLogTests(TestCase):
    def test_audit_log_is_created_when_settings_change(self):
        settings = ClinicSettings.load()
        settings.membership_due_reminder_days = 9
        settings.save()

        self.assertTrue(
            AuditLog.objects.filter(model_name="ClinicSettings", action=AuditLog.Action.UPDATED).exists()
        )
