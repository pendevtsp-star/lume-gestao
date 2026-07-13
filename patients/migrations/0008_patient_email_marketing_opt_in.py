from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0007_patient_referral_code_patientreferral"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="email_marketing_opt_in",
            field=models.BooleanField(
                default=False,
                help_text="Nao interfere em avisos operacionais, documentos, pagamentos ou recuperacao de acesso.",
                verbose_name="autoriza comunicacoes promocionais por e-mail",
            ),
        ),
        migrations.AddField(
            model_name="patient",
            name="email_marketing_opt_in_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="consentimento de marketing em"),
        ),
    ]
