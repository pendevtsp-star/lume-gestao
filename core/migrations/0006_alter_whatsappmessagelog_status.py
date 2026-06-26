from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_whatsappmessagelog_scheduled_for"),
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
                ],
                default="dry_run",
                max_length=20,
                verbose_name="status",
            ),
        ),
    ]
