from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_serviceplan_display_order_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceplan",
            name="deletion_requested_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="exclusao solicitada em"),
        ),
    ]
