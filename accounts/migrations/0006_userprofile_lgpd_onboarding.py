from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_userprofile_must_change_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="terms_accepted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="aceitou termos de uso em"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="privacy_policy_accepted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="aceitou politica de privacidade em"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="sensitive_data_consent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="consentiu dados sensiveis em"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="lgpd_consent_version",
            field=models.CharField(blank=True, max_length=20, verbose_name="versao do consentimento LGPD"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_message_sent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="credenciais enviadas em"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_delivery_method",
            field=models.CharField(blank=True, max_length=20, verbose_name="canal de envio das credenciais"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_delivery_error",
            field=models.TextField(blank=True, verbose_name="erro no envio das credenciais"),
        ),
    ]
