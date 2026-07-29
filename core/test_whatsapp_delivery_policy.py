from datetime import date, datetime, time, timedelta
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from billing.models import Charge, Membership, Payment, ServicePlan
from core.integrations.http import IntegrationError
from core.integrations.whatsapp import process_scheduled_whatsapp_messages
from core.integrations.whatsapp_provider import WhatsAppProviderError
from core.models import (
    WhatsAppAutomationRule,
    WhatsAppAutomationSettings,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from core.services.whatsapp_automation import enqueue_automatic_whatsapp_messages
from core.services.whatsapp_delivery_policy import (
    can_retry_manually,
    calculate_next_retry,
    evaluate_delivery,
)
from patients.models import Patient
from scheduling.models import Appointment, PatientNotification, PatientNotificationPreference
from team.models import Professional


@override_settings(
    WHATSAPP_WEB_GATEWAY_URL="http://gateway.local",
    WHATSAPP_DRY_RUN=False,
)
class WhatsAppDeliveryPolicyTests(TestCase):
    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 7, 29, 14, 54))
        self.patient = Patient.objects.create(
            full_name="Paciente Politica",
            phone="11999990000",
            birth_date=date(1990, 7, 29),
        )
        self.professional = Professional.objects.create(
            full_name="Dra. Politica",
            specialty=Professional.Specialty.PILATES,
        )
        self.integration = WhatsAppIntegration.objects.update_or_create(
            pk=1,
            defaults={
                "provider": WhatsAppIntegration.Provider.WEB_GATEWAY,
                "enabled": True,
                "dry_run": False,
                "clinic_whatsapp_number": "5511999990000",
            },
        )[0]
        WhatsAppMessageTemplate.ensure_defaults()
        self.appointment_template = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.APPOINTMENT
        )
        self.birthday_template = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.BIRTHDAY
        )
        self.charge_template = WhatsAppMessageTemplate.objects.get(
            template_type=WhatsAppMessageTemplate.TemplateType.CHARGE
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            professional=self.professional,
            starts_at=self.now + timedelta(minutes=6),
            ends_at=self.now + timedelta(hours=1, minutes=6),
            status=Appointment.Status.SCHEDULED,
        )

    def create_log(self, **overrides):
        values = {
            "integration": self.integration,
            "template": self.appointment_template,
            "patient": self.patient,
            "appointment": self.appointment,
            "recipient_name": self.patient.full_name,
            "recipient_number": self.patient.phone,
            "rendered_message": "Lembrete",
            "status": WhatsAppMessageLog.Status.SCHEDULED,
            "scheduled_for": self.now,
            "message_purpose": WhatsAppMessageLog.MessagePurpose.APPOINTMENT_CONFIRMATION,
            "retry_policy": WhatsAppMessageLog.RetryPolicy.UNTIL_EXPIRY,
            "expires_at": self.appointment.starts_at,
            "max_attempts": 4,
        }
        values.update(overrides)
        return WhatsAppMessageLog.objects.create(**values)

    def test_appointment_is_not_sent_at_or_after_its_start(self):
        log = self.create_log()

        decision = evaluate_delivery(log, now=self.appointment.starts_at)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.terminal_status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(decision.reason_code, "appointment_started")

    def test_canceled_appointment_is_not_sent(self):
        log = self.create_log()
        self.appointment.status = Appointment.Status.CANCELED
        self.appointment.save(update_fields=["status", "updated_at"])

        decision = evaluate_delivery(log, now=self.now)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "appointment_canceled")

    def test_rescheduled_appointment_does_not_send_message_with_old_time(self):
        log = self.create_log()
        self.appointment.starts_at += timedelta(hours=2)
        self.appointment.ends_at += timedelta(hours=2)
        self.appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])

        decision = evaluate_delivery(log, now=self.now)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "appointment_rescheduled")

    def test_paid_payment_is_not_sent(self):
        plan = ServicePlan.objects.create(
            name="Plano Politica",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("320.00"),
        )
        membership = Membership.objects.create(patient=self.patient, plan=plan, due_day=29)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 7, 1),
            due_date=date(2026, 7, 29),
            amount=Decimal("320.00"),
            status=Payment.Status.PAID,
            paid_at=date(2026, 7, 29),
        )
        log = self.create_log(
            template=self.charge_template,
            appointment=None,
            payment=payment,
            message_purpose=WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_DUE,
            retry_policy=WhatsAppMessageLog.RetryPolicy.BOUNDED,
            expires_at=timezone.make_aware(datetime.combine(payment.due_date, time.max)),
        )

        decision = evaluate_delivery(log, now=self.now)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "payment_settled")

    def test_received_charge_is_not_sent(self):
        charge = Charge.objects.create(
            patient=self.patient,
            description="Avaliacao",
            due_date=date(2026, 7, 28),
            amount=Decimal("150.00"),
            status=Charge.Status.RECEIVED,
            received_at=date(2026, 7, 29),
        )
        log = self.create_log(
            template=self.charge_template,
            appointment=None,
            charge=charge,
            message_purpose=WhatsAppMessageLog.MessagePurpose.CHARGE_OVERDUE,
            retry_policy=WhatsAppMessageLog.RetryPolicy.BOUNDED,
            expires_at=timezone.make_aware(datetime.combine(self.now.date(), time.max)),
        )

        decision = evaluate_delivery(log, now=self.now)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "charge_settled")

    def test_birthday_message_is_not_sent_on_next_day(self):
        log = self.create_log(
            template=self.birthday_template,
            appointment=None,
            message_purpose=WhatsAppMessageLog.MessagePurpose.BIRTHDAY,
            expires_at=timezone.make_aware(datetime.combine(self.now.date(), time.max)),
        )

        decision = evaluate_delivery(log, now=self.now + timedelta(days=1))

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "birthday_date_passed")

    def test_patient_opt_out_is_revalidated(self):
        log = self.create_log()
        PatientNotificationPreference.objects.create(
            patient=self.patient,
            whatsapp_enabled=False,
        )

        decision = evaluate_delivery(log, now=self.now)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "whatsapp_opt_out")

    def test_manual_retry_of_paid_payment_is_rejected(self):
        plan = ServicePlan.objects.create(
            name="Plano Manual",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("250.00"),
        )
        membership = Membership.objects.create(patient=self.patient, plan=plan, due_day=29)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 7, 1),
            due_date=date(2026, 7, 29),
            amount=Decimal("250.00"),
            status=Payment.Status.PAID,
            paid_at=date(2026, 7, 29),
        )
        log = self.create_log(
            appointment=None,
            payment=payment,
            message_purpose=WhatsAppMessageLog.MessagePurpose.MANUAL,
            retry_policy=WhatsAppMessageLog.RetryPolicy.NONE,
            expires_at=None,
            status=WhatsAppMessageLog.Status.FAILED,
        )

        decision = can_retry_manually(log, now=self.now)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "payment_settled")

    def test_notification_retry_action_rejects_expired_appointment(self):
        user = get_user_model().objects.create_user(
            username="gestor-politica",
            password="Senha@123",
        )
        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.MANAGEMENT},
        )
        action_now = timezone.now()
        self.appointment.starts_at = action_now - timedelta(minutes=5)
        self.appointment.ends_at = action_now + timedelta(minutes=55)
        self.appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
        log = self.create_log(
            status=WhatsAppMessageLog.Status.FAILED,
            expires_at=self.appointment.starts_at,
        )
        notification = PatientNotification.objects.create(
            patient=self.patient,
            appointment=self.appointment,
            delivery_log=log,
            kind=PatientNotification.Kind.SESSION_CONFIRMATION,
            channel=PatientNotification.Channel.WHATSAPP,
            due_at=self.now,
            idempotency_key="expired-retry-action",
            message="Lembrete",
            status=PatientNotification.Status.FAILED,
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("scheduling:notification_retry", args=[notification.pk])
        )
        log.refresh_from_db()
        notification.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(log.terminal_reason, "appointment_started")
        self.assertEqual(notification.status, PatientNotification.Status.SKIPPED)

    def test_retry_is_calculated_only_before_expiry(self):
        log = self.create_log(attempt_count=1)

        retry_at = calculate_next_retry(
            log,
            now=self.now,
            retryable=True,
        )

        self.assertEqual(retry_at, self.now + timedelta(minutes=2))

    def test_retry_after_expiry_is_rejected(self):
        log = self.create_log(attempt_count=2, expires_at=self.now + timedelta(minutes=4))

        retry_at = calculate_next_retry(
            log,
            now=self.now,
            retryable=True,
        )

        self.assertIsNone(retry_at)

    def test_manual_message_never_retries_automatically(self):
        log = self.create_log(
            appointment=None,
            message_purpose=WhatsAppMessageLog.MessagePurpose.MANUAL,
            retry_policy=WhatsAppMessageLog.RetryPolicy.NONE,
            expires_at=None,
            max_attempts=1,
        )

        retry_at = calculate_next_retry(
            log,
            now=self.now,
            retryable=True,
        )

        self.assertIsNone(retry_at)
        self.assertTrue(can_retry_manually(log, now=self.now).allowed)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_expired_appointment_finishes_without_calling_provider(self, send_mock):
        log = self.create_log()
        notification = PatientNotification.objects.create(
            patient=self.patient,
            appointment=self.appointment,
            delivery_log=log,
            kind=PatientNotification.Kind.SESSION_CONFIRMATION,
            channel=PatientNotification.Channel.WHATSAPP,
            due_at=self.now,
            idempotency_key="expired-notification",
            message="Lembrete",
        )

        summary = process_scheduled_whatsapp_messages(now=self.appointment.starts_at)
        log.refresh_from_db()
        notification.refresh_from_db()

        send_mock.assert_not_called()
        self.assertEqual(summary["expired"], 1)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(log.terminal_reason, "appointment_started")
        self.assertIsNone(log.lease_until)
        self.assertEqual(notification.status, PatientNotification.Status.SKIPPED)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_canceled_appointment_between_enqueue_and_send_skips_provider(self, send_mock):
        log = self.create_log()
        self.appointment.status = Appointment.Status.CANCELED
        self.appointment.save(update_fields=["status", "updated_at"])

        process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        send_mock.assert_not_called()
        self.assertEqual(log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(log.terminal_reason, "appointment_canceled")

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_rescheduled_appointment_between_enqueue_and_send_skips_provider(self, send_mock):
        log = self.create_log()
        self.appointment.starts_at += timedelta(hours=1)
        self.appointment.ends_at += timedelta(hours=1)
        self.appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])

        process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        send_mock.assert_not_called()
        self.assertEqual(log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(log.terminal_reason, "appointment_rescheduled")

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_payment_settled_between_enqueue_and_send_skips_provider(self, send_mock):
        plan = ServicePlan.objects.create(
            name="Plano Fila",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("280.00"),
        )
        membership = Membership.objects.create(patient=self.patient, plan=plan, due_day=29)
        payment = Payment.objects.create(
            membership=membership,
            reference_month=date(2026, 7, 1),
            due_date=date(2026, 7, 29),
            amount=Decimal("280.00"),
        )
        log = self.create_log(
            template=self.charge_template,
            appointment=None,
            payment=payment,
            message_purpose=WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_DUE,
            retry_policy=WhatsAppMessageLog.RetryPolicy.BOUNDED,
            expires_at=timezone.make_aware(datetime.combine(payment.due_date, time.max)),
        )
        payment.status = Payment.Status.PAID
        payment.paid_at = date(2026, 7, 29)
        payment.save(update_fields=["status", "paid_at", "updated_at"])

        process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        send_mock.assert_not_called()
        self.assertEqual(log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(log.terminal_reason, "payment_settled")

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_birthday_queued_yesterday_skips_provider(self, send_mock):
        yesterday = self.now.date() - timedelta(days=1)
        self.patient.birth_date = self.patient.birth_date.replace(
            month=yesterday.month,
            day=yesterday.day,
        )
        self.patient.save(update_fields=["birth_date", "updated_at"])
        log = self.create_log(
            template=self.birthday_template,
            appointment=None,
            message_purpose=WhatsAppMessageLog.MessagePurpose.BIRTHDAY,
            expires_at=timezone.make_aware(datetime.combine(yesterday, time.max)),
        )

        process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        send_mock.assert_not_called()
        self.assertEqual(log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(log.terminal_reason, "birthday_date_passed")

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_retry_preserves_original_schedule_and_releases_lease(self, send_mock):
        send_mock.side_effect = WhatsAppProviderError(
            "Gateway indisponível.",
            code="SESSION_NOT_READY",
            retryable=True,
        )
        log = self.create_log()
        original_schedule = log.scheduled_for

        summary = process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        self.assertEqual(summary["retried"], 1)
        self.assertEqual(log.scheduled_for, original_schedule)
        self.assertEqual(log.next_attempt_at, self.now + timedelta(minutes=2))
        self.assertIsNone(log.lease_until)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_retry_past_expiry_marks_message_expired(self, send_mock):
        send_mock.side_effect = WhatsAppProviderError(
            "Gateway indisponível.",
            code="SESSION_NOT_READY",
            retryable=True,
        )
        self.appointment.starts_at = self.now + timedelta(minutes=1)
        self.appointment.ends_at = self.appointment.starts_at + timedelta(hours=1)
        self.appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
        log = self.create_log(expires_at=self.appointment.starts_at)

        summary = process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        self.assertEqual(summary["expired"], 1)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(log.terminal_reason, "retry_after_expiry")
        self.assertIsNone(log.next_attempt_at)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_permanent_error_does_not_retry(self, send_mock):
        send_mock.side_effect = IntegrationError("Numero invalido.")
        log = self.create_log()

        summary = process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        self.assertEqual(summary["failed"], 1)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.FAILED)
        self.assertIsNone(log.next_attempt_at)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_failed_manual_send_does_not_retry_automatically(self, send_mock):
        send_mock.side_effect = WhatsAppProviderError(
            "Gateway indisponível.",
            code="SESSION_NOT_READY",
            retryable=True,
        )
        log = self.create_log(
            appointment=None,
            message_purpose=WhatsAppMessageLog.MessagePurpose.MANUAL,
            retry_policy=WhatsAppMessageLog.RetryPolicy.NONE,
            expires_at=None,
            max_attempts=1,
        )

        summary = process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        self.assertEqual(summary["retried"], 0)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.FAILED)
        self.assertIsNone(log.next_attempt_at)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_uncertain_delivery_never_retries_or_becomes_sent(self, send_mock):
        send_mock.side_effect = WhatsAppProviderError(
            "Resultado da entrega desconhecido.",
            code="DELIVERY_RESULT_UNKNOWN",
            delivery_uncertain=True,
        )
        log = self.create_log()

        first = process_scheduled_whatsapp_messages(now=self.now)
        second = process_scheduled_whatsapp_messages(now=self.now + timedelta(minutes=2))
        log.refresh_from_db()

        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(first["uncertain"], 1)
        self.assertEqual(second["processed"], 0)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN)
        self.assertEqual(log.terminal_reason, "provider_result_unknown")
        self.assertIsNone(log.next_attempt_at)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_uncertain_delivery_finishes_linked_notification(self, send_mock):
        send_mock.side_effect = WhatsAppProviderError(
            "Resultado da entrega desconhecido.",
            code="DELIVERY_RESULT_UNKNOWN",
            delivery_uncertain=True,
        )
        log = self.create_log()
        notification = PatientNotification.objects.create(
            patient=self.patient,
            appointment=self.appointment,
            delivery_log=log,
            kind=PatientNotification.Kind.SESSION_CONFIRMATION,
            channel=PatientNotification.Channel.WHATSAPP,
            due_at=self.now,
            idempotency_key="uncertain-notification",
            message="Lembrete",
        )

        process_scheduled_whatsapp_messages(now=self.now)
        notification.refresh_from_db()

        self.assertEqual(notification.status, PatientNotification.Status.FAILED)
        self.assertTrue(notification.metadata["delivery_uncertain"])
        self.assertEqual(notification.attempts, 1)

    @patch("core.integrations.whatsapp.send_whatsapp_text")
    def test_lease_prevents_two_workers_from_sending_same_log(self, send_mock):
        log = self.create_log()
        nested_summaries = []

        def send_with_competing_worker(*args, **kwargs):
            if not nested_summaries:
                nested_summaries.append(process_scheduled_whatsapp_messages(now=self.now))
            return {"ok": True, "messageId": "single-send"}

        send_mock.side_effect = send_with_competing_worker

        summary = process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(nested_summaries[0]["processed"], 0)
        self.assertEqual(summary["sent"], 1)
        self.assertIsNone(log.lease_until)

    def test_automation_intent_is_created_while_gateway_is_disconnected(self):
        self.integration.enabled = False
        self.integration.save(update_fields=["enabled", "updated_at"])
        settings = WhatsAppAutomationSettings.load()
        settings.birthday_messages_enabled = False
        settings.save(update_fields=["birthday_messages_enabled", "updated_at"])
        WhatsAppAutomationRule.ensure_defaults()
        rule = WhatsAppAutomationRule.objects.get(
            template__template_type=WhatsAppMessageTemplate.TemplateType.SESSION_SOON,
            is_system=True,
        )
        self.appointment.starts_at = self.now + timedelta(hours=rule.hours_before, minutes=10)
        self.appointment.ends_at = self.appointment.starts_at + timedelta(hours=1)
        self.appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])

        created = enqueue_automatic_whatsapp_messages(now=self.now)
        log = WhatsAppMessageLog.objects.get(appointment=self.appointment)

        self.assertEqual(created["appointment_day"], 1)
        self.assertEqual(log.message_purpose, WhatsAppMessageLog.MessagePurpose.APPOINTMENT_SOON)
        self.assertEqual(log.retry_policy, WhatsAppMessageLog.RetryPolicy.UNTIL_EXPIRY)
        self.assertEqual(log.expires_at, self.appointment.starts_at)
        self.assertEqual(log.max_attempts, 4)
        self.assertTrue(log.automation_key)

        summary = process_scheduled_whatsapp_messages(now=self.now)
        log.refresh_from_db()

        self.assertEqual(summary["retried"], 1)
        self.assertEqual(log.status, WhatsAppMessageLog.Status.SCHEDULED)
        self.assertEqual(log.next_attempt_at, self.now + timedelta(minutes=2))

    def test_data_migration_preserves_and_classifies_existing_logs(self):
        self.appointment.starts_at = timezone.now() + timedelta(days=1)
        self.appointment.ends_at = self.appointment.starts_at + timedelta(hours=1)
        self.appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
        future_log = self.create_log(
            message_purpose=WhatsAppMessageLog.MessagePurpose.MANUAL,
            retry_policy=WhatsAppMessageLog.RetryPolicy.NONE,
            expires_at=None,
            max_attempts=1,
        )
        manual_log = self.create_log(
            appointment=None,
            message_purpose=WhatsAppMessageLog.MessagePurpose.MANUAL,
            retry_policy=WhatsAppMessageLog.RetryPolicy.NONE,
            expires_at=None,
            max_attempts=1,
            status=WhatsAppMessageLog.Status.FAILED,
        )
        yesterday = timezone.localdate() - timedelta(days=1)
        old_birthday_log = self.create_log(
            template=self.birthday_template,
            appointment=None,
            automation_key=f"birthday:{self.patient.pk}:{yesterday.isoformat()}",
            message_purpose=WhatsAppMessageLog.MessagePurpose.MANUAL,
            retry_policy=WhatsAppMessageLog.RetryPolicy.NONE,
            expires_at=None,
            max_attempts=1,
        )
        original_ids = set(WhatsAppMessageLog.objects.values_list("pk", flat=True))
        migration = import_module("core.migrations.0017_whatsapp_delivery_policy")

        migration.backfill_delivery_policy(apps, None)
        future_log.refresh_from_db()
        manual_log.refresh_from_db()
        old_birthday_log.refresh_from_db()

        self.assertSetEqual(
            set(WhatsAppMessageLog.objects.values_list("pk", flat=True)),
            original_ids,
        )
        self.assertEqual(
            future_log.message_purpose,
            WhatsAppMessageLog.MessagePurpose.APPOINTMENT_CONFIRMATION,
        )
        self.assertEqual(
            future_log.retry_policy,
            WhatsAppMessageLog.RetryPolicy.UNTIL_EXPIRY,
        )
        self.assertEqual(future_log.expires_at, self.appointment.starts_at)
        self.assertEqual(manual_log.message_purpose, WhatsAppMessageLog.MessagePurpose.MANUAL)
        self.assertEqual(manual_log.retry_policy, WhatsAppMessageLog.RetryPolicy.NONE)
        self.assertEqual(
            old_birthday_log.message_purpose,
            WhatsAppMessageLog.MessagePurpose.BIRTHDAY,
        )
        self.assertEqual(old_birthday_log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(old_birthday_log.terminal_reason, "birthday_date_passed")

    def test_reverse_migration_never_requeues_or_reclassifies_terminal_logs(self):
        expired_log = self.create_log(
            status=WhatsAppMessageLog.Status.EXPIRED,
            terminal_reason="appointment_started",
        )
        uncertain_log = self.create_log(
            status=WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN,
            terminal_reason="provider_result_unknown",
        )
        migration = import_module("core.migrations.0017_whatsapp_delivery_policy")

        migration.reverse_delivery_policy_backfill(apps, None)
        expired_log.refresh_from_db()
        uncertain_log.refresh_from_db()

        self.assertEqual(expired_log.status, WhatsAppMessageLog.Status.EXPIRED)
        self.assertEqual(
            uncertain_log.status,
            WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN,
        )
