from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_whatsappautomationsettings_appointment_day_reminder_hours_before_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailDeliveryEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("provider", models.CharField(default="brevo", max_length=40, verbose_name="provedor")),
                ("event_type", models.CharField(db_index=True, max_length=60, verbose_name="evento")),
                ("recipient", models.EmailField(blank=True, max_length=254, verbose_name="destinatario")),
                ("message_id", models.CharField(blank=True, db_index=True, max_length=255, verbose_name="identificador da mensagem")),
                ("occurred_at", models.DateTimeField(blank=True, null=True, verbose_name="ocorreu em")),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="dados do provedor")),
            ],
            options={
                "verbose_name": "evento de entrega de e-mail",
                "verbose_name_plural": "eventos de entrega de e-mail",
                "ordering": ["-occurred_at", "-created_at"],
            },
        ),
    ]
