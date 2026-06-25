from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_userprofile_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="whatsapp_number",
            field=models.CharField(blank=True, max_length=30, verbose_name="WhatsApp administrativo"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="whatsapp_notifications_enabled",
            field=models.BooleanField(default=False, verbose_name="habilitar avisos por WhatsApp"),
        ),
    ]
