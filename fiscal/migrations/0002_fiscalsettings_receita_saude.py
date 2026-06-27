from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="fiscalsettings",
            name="receita_saude_enabled",
            field=models.BooleanField(default=False, verbose_name="usar assistente Receita Saude"),
        ),
        migrations.AddField(
            model_name="fiscalsettings",
            name="receita_saude_notes",
            field=models.TextField(blank=True, verbose_name="orientacoes internas Receita Saude"),
        ),
    ]
