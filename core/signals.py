from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from core.audit import get_current_user, instance_snapshot
from core.models import AuditLog

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
