from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_googlecalendarintegration_oauth_credentials"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappintegration",
            name="embedded_app_id",
            field=models.CharField(blank=True, max_length=80, verbose_name="Meta App ID"),
        ),
        migrations.AddField(
            model_name="whatsappintegration",
            name="embedded_config_id",
            field=models.CharField(blank=True, max_length=120, verbose_name="Meta Configuration ID"),
        ),
        migrations.AddField(
            model_name="whatsappintegration",
            name="embedded_app_secret",
            field=models.CharField(blank=True, max_length=255, verbose_name="Meta App Secret"),
        ),
        migrations.AddField(
            model_name="whatsappintegration",
            name="access_token",
            field=models.TextField(blank=True, verbose_name="token de acesso Meta"),
        ),
    ]
