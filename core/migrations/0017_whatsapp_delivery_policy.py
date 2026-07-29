import uuid
from datetime import date, datetime, time

from django.db import migrations, models
from django.utils import timezone


APPOINTMENT_PURPOSE_BY_TEMPLATE = {
    "appointment": "appointment_confirmation",
    "session_soon": "appointment_soon",
}


def end_of_local_day(day):
    return timezone.make_aware(
        datetime.combine(day, time.max),
        timezone.get_current_timezone(),
    )


def automation_policy(log, apps):
    key_parts = (log.automation_key or "").split(":")
    if len(key_parts) == 3 and key_parts[0] == "birthday":
        try:
            expiry_day = date.fromisoformat(key_parts[2])
        except ValueError:
            return None
        return "birthday", "until_expiry", end_of_local_day(expiry_day)

    if len(key_parts) == 4 and key_parts[0] == "payment" and log.payment_id:
        counter_key = key_parts[2]
        if counter_key not in {"membership_due", "membership_overdue"}:
            return None
        purpose = counter_key
        expiry_day = (
            timezone.localtime(log.created_at).date()
            if counter_key == "membership_overdue"
            else log.payment.due_date
        )
        return purpose, "bounded", end_of_local_day(expiry_day)

    if len(key_parts) == 4 and key_parts[0] == "membership-receivable":
        counter_key = key_parts[3]
        if counter_key not in {"membership_due", "membership_overdue"}:
            return None
        try:
            membership_id = int(key_parts[1])
            reference_month = date.fromisoformat(key_parts[2])
        except ValueError:
            return None
        Membership = apps.get_model("billing", "Membership")
        membership = Membership.objects.filter(pk=membership_id).first()
        if not membership:
            return None
        expiry_day = (
            timezone.localtime(log.created_at).date()
            if counter_key == "membership_overdue"
            else reference_month.replace(day=min(membership.due_day, 28))
        )
        return counter_key, "bounded", end_of_local_day(expiry_day)

    if (
        len(key_parts) == 4
        and key_parts[0] == "charge"
        and key_parts[2] == "charge_overdue"
        and log.charge_id
    ):
        try:
            expiry_day = date.fromisoformat(key_parts[3])
        except ValueError:
            return None
        return "charge_overdue", "bounded", end_of_local_day(expiry_day)

    return None


def backfill_delivery_policy(apps, schema_editor):
    WhatsAppMessageLog = apps.get_model("core", "WhatsAppMessageLog")
    now = timezone.now()
    classified = 0
    expired = 0

    for log in WhatsAppMessageLog.objects.select_related(
        "appointment",
        "template",
        "payment",
        "charge",
    ).iterator():
        update_fields = ["delivery_request_id"]
        log.delivery_request_id = uuid.uuid4()

        if log.status == "scheduled" and log.appointment_id:
            appointment = log.appointment
            log.expires_at = appointment.starts_at
            template_type = log.template.template_type if log.template_id else ""
            log.message_purpose = APPOINTMENT_PURPOSE_BY_TEMPLATE.get(
                template_type,
                "appointment_confirmation",
            )
            log.retry_policy = "until_expiry"
            log.max_attempts = 4
            update_fields.extend(
                [
                    "expires_at",
                    "message_purpose",
                    "retry_policy",
                    "max_attempts",
                ]
            )
            if appointment.starts_at <= now:
                log.status = "expired"
                log.next_attempt_at = None
                log.lease_until = None
                log.terminal_reason = "appointment_started"
                update_fields.extend(
                    [
                        "status",
                        "next_attempt_at",
                        "lease_until",
                        "terminal_reason",
                    ]
                )
                expired += 1
            else:
                classified += 1
        elif log.status == "scheduled":
            policy = automation_policy(log, apps)
            if policy:
                purpose, retry_policy, expires_at = policy
                log.message_purpose = purpose
                log.retry_policy = retry_policy
                log.expires_at = expires_at
                log.max_attempts = 4
                update_fields.extend(
                    [
                        "message_purpose",
                        "retry_policy",
                        "expires_at",
                        "max_attempts",
                    ]
                )
                if expires_at <= now:
                    log.status = "expired"
                    log.next_attempt_at = None
                    log.lease_until = None
                    log.terminal_reason = (
                        "birthday_date_passed"
                        if purpose == "birthday"
                        else "validity_expired"
                    )
                    update_fields.extend(
                        [
                            "status",
                            "next_attempt_at",
                            "lease_until",
                            "terminal_reason",
                        ]
                    )
                    expired += 1
                else:
                    classified += 1

        log.save(update_fields=update_fields)

    unclassified = WhatsAppMessageLog.objects.filter(message_purpose="manual").count()
    print(
        "WhatsApp delivery policy backfill: "
        f"{classified} log(s) automatico(s) classificados; "
        f"{expired} log(s) automatico(s) expirados; "
        f"{unclassified} log(s) preservados como manuais para revisao."
    )


def reverse_delivery_policy_backfill(apps, schema_editor):
    # Terminal delivery outcomes must never be restored to a retryable state.
    # Keeping the row untouched also preserves the evidence needed for audit
    # and for a safe forward migration after a code rollback.
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_force_whatsapp_web_and_unique_automation_keys"),
    ]

    operations = [
        migrations.AlterField(
            model_name="whatsappmessagelog",
            name="status",
            field=models.CharField(
                choices=[
                    ("scheduled", "Agendada"),
                    ("sent", "Enviada"),
                    ("dry_run", "Simulada"),
                    ("failed", "Falhou"),
                    ("canceled", "Cancelada"),
                    ("expired", "Prazo encerrado"),
                    ("delivery_uncertain", "Entrega incerta"),
                ],
                default="dry_run",
                max_length=20,
                verbose_name="status",
            ),
        ),
        migrations.AddField(
            model_name="whatsappmessagelog",
            name="delivery_request_id",
            field=models.UUIDField(editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="whatsappmessagelog",
            name="expires_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="expira em",
            ),
        ),
        migrations.AddField(
            model_name="whatsappmessagelog",
            name="lease_until",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name="reservada ate",
            ),
        ),
        migrations.AddField(
            model_name="whatsappmessagelog",
            name="max_attempts",
            field=models.PositiveSmallIntegerField(
                default=1,
                verbose_name="limite de tentativas",
            ),
        ),
        migrations.AddField(
            model_name="whatsappmessagelog",
            name="message_purpose",
            field=models.CharField(
                choices=[
                    ("manual", "Envio manual"),
                    ("appointment_confirmation", "Confirmacao de sessao"),
                    ("appointment_soon", "Sessao proxima"),
                    ("birthday", "Aniversario"),
                    ("membership_due", "Mensalidade a vencer"),
                    ("membership_overdue", "Mensalidade vencida"),
                    ("charge_overdue", "Cobranca avulsa vencida"),
                ],
                default="manual",
                max_length=40,
                verbose_name="finalidade",
            ),
        ),
        migrations.AddField(
            model_name="whatsappmessagelog",
            name="retry_policy",
            field=models.CharField(
                choices=[
                    ("none", "Sem tentativa automatica"),
                    ("until_expiry", "Tentar somente enquanto for util"),
                    ("bounded", "Tentativas limitadas"),
                ],
                default="none",
                max_length=20,
                verbose_name="politica de retentativa",
            ),
        ),
        migrations.AddField(
            model_name="whatsappmessagelog",
            name="terminal_reason",
            field=models.CharField(
                blank=True,
                max_length=60,
                verbose_name="motivo terminal",
            ),
        ),
        migrations.RunPython(
            backfill_delivery_policy,
            reverse_delivery_policy_backfill,
        ),
        migrations.AlterField(
            model_name="whatsappmessagelog",
            name="delivery_request_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
