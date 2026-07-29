from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from core.models import WhatsAppMessageTemplate


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
