from datetime import date, datetime, time
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Membership, Payment, ServicePlan
from core.models import (
    WhatsAppAutomationSettings,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from core.services.whatsapp_automation import enqueue_automatic_whatsapp_messages
from patients.models import Patient


class FinancialWhatsAppTemplateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="gestao-modelos-financeiros",
            password="Senha@123",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"role": UserProfile.Role.MANAGEMENT},
        )
        self.client.force_login(self.user)
        WhatsAppMessageTemplate.ensure_defaults()

    def test_four_financial_automations_have_independent_templates(self):
        template_types = [
            WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE,
            WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE_DATE,
            WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_OVERDUE,
            WhatsAppMessageTemplate.TemplateType.CHARGE_OVERDUE,
        ]

        self.assertEqual(
            WhatsAppMessageTemplate.objects.filter(
                template_type__in=template_types
            ).count(),
            4,
        )
        self.assertEqual(len(set(template_types)), 4)

    def test_editing_membership_due_does_not_change_other_financial_messages(self):
        due = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE
        )
        due_date = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE_DATE
        )
        overdue = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_OVERDUE
        )
        charge = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.CHARGE_OVERDUE
        )
        original_other_bodies = [due_date.body, overdue.body, charge.body]
        new_body = (
            "Olá, [Paciente]! Sua mensalidade de [Valor] vence em "
            "[DataVencimento]. Equipe [Clinica]."
        )

        response = self.client.post(
            reverse("relationships:automations"),
            {
                "automation_key": "membership_due",
                "membership_due-enabled": "on",
                "membership_due-timing": "3",
                "membership_due-body": new_body,
            },
        )

        self.assertRedirects(response, reverse("relationships:automations"))
        due.refresh_from_db()
        due_date.refresh_from_db()
        overdue.refresh_from_db()
        charge.refresh_from_db()
        self.assertEqual(due.body, new_body)
        self.assertEqual(
            [due_date.body, overdue.body, charge.body],
            original_other_bodies,
        )

    def test_data_migration_copies_legacy_charge_body_without_deleting_it(self):
        legacy = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.CHARGE
        )
        legacy.body = "Texto financeiro personalizado [Paciente] [Valor] [DataVencimento]"
        legacy.save(update_fields=["body", "updated_at"])
        WhatsAppMessageTemplate.objects.exclude(pk=legacy.pk).filter(
            template_type__in=[
                WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE,
                WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE_DATE,
                WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_OVERDUE,
                WhatsAppMessageTemplate.TemplateType.CHARGE_OVERDUE,
            ]
        ).delete()
        migration = import_module("core.migrations.0018_financial_whatsapp_templates")

        migration.copy_financial_templates(apps, None)

        legacy.refresh_from_db()
        self.assertEqual(
            WhatsAppMessageTemplate.objects.filter(
                template_type__in=[
                    WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE,
                    WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE_DATE,
                    WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_OVERDUE,
                    WhatsAppMessageTemplate.TemplateType.CHARGE_OVERDUE,
                ],
                body=legacy.body,
            ).count(),
            4,
        )
        self.assertTrue(
            WhatsAppMessageTemplate.objects.filter(pk=legacy.pk).exists()
        )

    def test_due_date_message_has_distinct_idempotency_from_advance_reminder(self):
        patient = Patient.objects.create(
            full_name="Paciente Vencimento",
            phone="11999990000",
        )
        plan = ServicePlan.objects.create(
            name="Plano Vencimento",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("250.00"),
        )
        membership = Membership.objects.create(
            patient=patient,
            plan=plan,
            due_day=29,
        )
        today = date(2026, 7, 29)
        Payment.objects.create(
            membership=membership,
            reference_month=today.replace(day=1),
            due_date=today,
            amount=Decimal("250.00"),
            status=Payment.Status.PENDING,
        )
        WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={"enabled": True, "dry_run": True},
        )
        automation = WhatsAppAutomationSettings.load()
        automation.membership_due_reminders_enabled = True
        automation.membership_due_days_before = 0
        automation.membership_due_on_date = True
        automation.membership_overdue_enabled = False
        automation.charge_overdue_enabled = False
        automation.birthday_messages_enabled = False
        automation.save()
        now = timezone.make_aware(datetime.combine(today, time(12, 0)))

        enqueue_automatic_whatsapp_messages(now=now)

        logs = WhatsAppMessageLog.objects.filter(payment__isnull=False)
        self.assertEqual(logs.count(), 2)
        self.assertEqual(
            set(logs.values_list("template__template_type", flat=True)),
            {
                WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE,
                WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE_DATE,
            },
        )

    @patch(
        "relationships.web.automations.WhatsAppAutomationRule.sync_system_rules",
        side_effect=RuntimeError("synthetic rule failure"),
    )
    def test_automation_settings_and_template_update_atomically(self, _sync_rules):
        settings_object = WhatsAppAutomationSettings.load()
        original_hours = settings_object.appointment_reminder_hours_before
        template = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT
        )
        original_body = template.body

        with self.assertRaises(RuntimeError):
            self.client.post(
                reverse("relationships:automations"),
                {
                    "automation_key": "appointment_confirmation",
                    "appointment_confirmation-enabled": "on",
                    "appointment_confirmation-timing": "48",
                    "appointment_confirmation-body": (
                        "Olá, [Paciente]! Sessão em [Data], às [Horario]."
                    ),
                },
            )

        settings_object.refresh_from_db()
        template.refresh_from_db()
        self.assertEqual(
            settings_object.appointment_reminder_hours_before,
            original_hours,
        )
        self.assertEqual(template.body, original_body)
