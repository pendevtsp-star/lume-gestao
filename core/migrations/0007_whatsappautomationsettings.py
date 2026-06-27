import datetime

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_alter_whatsappmessagelog_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppAutomationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "appointment_reminders_enabled",
                    models.BooleanField(default=True, verbose_name="enviar lembretes de consulta automaticamente"),
                ),
                (
                    "appointment_reminder_hours_before",
                    models.PositiveSmallIntegerField(default=24, verbose_name="horas antes da consulta"),
                ),
                (
                    "birthday_messages_enabled",
                    models.BooleanField(default=True, verbose_name="enviar aniversarios automaticamente"),
                ),
                ("birthday_send_time", models.TimeField(default=datetime.time(8, 0), verbose_name="horario do aniversario")),
            ],
            options={
                "verbose_name": "automacao WhatsApp",
                "verbose_name_plural": "automacoes WhatsApp",
            },
        ),
    ]
