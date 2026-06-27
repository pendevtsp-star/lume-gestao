from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_whatsappautomationsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="googlecalendarintegration",
            name="oauth_client_id",
            field=models.CharField(blank=True, max_length=255, verbose_name="Google Client ID"),
        ),
        migrations.AddField(
            model_name="googlecalendarintegration",
            name="oauth_client_secret",
            field=models.CharField(blank=True, max_length=255, verbose_name="Google Client Secret"),
        ),
    ]
