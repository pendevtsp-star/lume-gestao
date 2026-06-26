from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from core.audit import get_current_user, instance_snapshot
from core.integrations.google_calendar import delete_google_event, sync_appointment_to_google
from core.integrations.http import IntegrationError
from core.models import AuditLog
from scheduling.models import Appointment

TRACKED_APPS = {"accounts", "patients", "team", "billing", "scheduling", "core"}
IGNORED_MODELS = {"AuditLog"}


def should_audit(instance):
    meta = instance._meta
    return meta.app_label in TRACKED_APPS and meta.object_name not in IGNORED_MODELS


@receiver(pre_save)
def capture_previous_state(sender, instance, **kwargs):
    if not should_audit(instance) or not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    instance._audit_previous = instance_snapshot(previous)


@receiver(post_save)
def write_save_audit(sender, instance, created, **kwargs):
    if not should_audit(instance):
        return

    current = instance_snapshot(instance)
    previous = getattr(instance, "_audit_previous", {})
    changes = {}

    if created:
        changes = {field: {"old": None, "new": value} for field, value in current.items()}
    else:
        for field, value in current.items():
            old_value = previous.get(field)
            if old_value != value:
                changes[field] = {"old": old_value, "new": value}

    if not changes and not created:
        return

    AuditLog.objects.create(
        actor=get_current_user(),
        action=AuditLog.Action.CREATED if created else AuditLog.Action.UPDATED,
        app_label=instance._meta.app_label,
        model_name=instance._meta.object_name,
        object_id=str(instance.pk or ""),
        object_repr=str(instance)[:255],
        changes=changes,
    )


@receiver(post_delete)
def write_delete_audit(sender, instance, **kwargs):
    if not should_audit(instance):
        return

    AuditLog.objects.create(
        actor=get_current_user(),
        action=AuditLog.Action.DELETED,
        app_label=instance._meta.app_label,
        model_name=instance._meta.object_name,
        object_id=str(instance.pk or ""),
        object_repr=str(instance)[:255],
        changes={},
    )


def google_sync_enabled():
    return bool(settings.GOOGLE_CALENDAR_SYNC_ENABLED)


def record_google_sync_error(message):
    from core.models import GoogleCalendarIntegration

    integration = GoogleCalendarIntegration.load()
    integration.last_error = str(message)
    integration.save(update_fields=["last_error", "updated_at"])


@receiver(post_save, sender=Appointment)
def sync_appointment_after_commit(sender, instance, **kwargs):
    if getattr(instance, "_skip_google_sync", False):
        return
    if kwargs.get("raw") or not google_sync_enabled():
        return

    def _sync():
        from core.models import GoogleCalendarIntegration

        integration = GoogleCalendarIntegration.load()
        if not integration.enabled or not integration.sync_on_save or not integration.is_connected:
            return
        try:
            appointment = Appointment.objects.select_related("patient", "professional").get(pk=instance.pk)
            sync_appointment_to_google(appointment, integration=integration)
        except Appointment.DoesNotExist:
            return
        except IntegrationError as exc:
            record_google_sync_error(exc)

    transaction.on_commit(_sync)


@receiver(post_delete, sender=Appointment)
def delete_google_appointment_after_commit(sender, instance, **kwargs):
    if kwargs.get("raw") or not google_sync_enabled():
        return
    if instance.external_provider != "google" or not instance.external_event_id:
        return

    event_id = instance.external_event_id

    def _delete():
        from core.models import GoogleCalendarIntegration

        integration = GoogleCalendarIntegration.load()
        if not integration.enabled or not integration.sync_on_save or not integration.is_connected:
            return
        try:
            delete_google_event(event_id, integration=integration)
        except IntegrationError as exc:
            record_google_sync_error(exc)

    transaction.on_commit(_delete)
