from django.db import migrations, models
from django.db.models import Count, Q


def force_whatsapp_web_and_dedupe_keys(apps, schema_editor):
    WhatsAppIntegration = apps.get_model("core", "WhatsAppIntegration")
    WhatsAppMessageLog = apps.get_model("core", "WhatsAppMessageLog")

    WhatsAppIntegration.objects.update(provider="web_gateway")

    duplicate_keys = (
        WhatsAppMessageLog.objects.exclude(automation_key="")
        .exclude(status="canceled")
        .values("automation_key")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    for item in duplicate_keys:
        logs = list(
            WhatsAppMessageLog.objects.filter(automation_key=item["automation_key"])
            .exclude(status="canceled")
            .order_by("created_at", "id")
        )
        for duplicate in logs[1:]:
            base_key = duplicate.automation_key[:150]
            duplicate.automation_key = f"{base_key}:duplicate:{duplicate.pk}"
            duplicate.save(update_fields=["automation_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0015_whatsappmessagelog_delivery_retry"),
    ]

    operations = [
        migrations.RunPython(force_whatsapp_web_and_dedupe_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="whatsappintegration",
            name="provider",
            field=models.CharField(
                choices=[
                    ("meta", "Meta Cloud API"),
                    ("web_gateway", "WhatsApp Web"),
                    ("twilio", "Twilio"),
                ],
                default="web_gateway",
                max_length=20,
                verbose_name="provedor",
            ),
        ),
        migrations.AddConstraint(
            model_name="whatsappmessagelog",
            constraint=models.UniqueConstraint(
                condition=~Q(automation_key="") & ~Q(status="canceled"),
                fields=("automation_key",),
                name="unique_active_whatsapp_automation_key",
            ),
        ),
    ]
