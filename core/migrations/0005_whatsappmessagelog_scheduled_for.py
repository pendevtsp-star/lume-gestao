from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_whatsappintegration_clinic_whatsapp_number_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappmessagelog",
            name="scheduled_for",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="agendada para"),
        ),
    ]
