from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0005_professionalnote_structured_data_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="deletion_requested_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="exclusao solicitada em"),
        ),
    ]
