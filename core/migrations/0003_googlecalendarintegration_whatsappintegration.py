from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_clinicsettings_address_clinicsettings_business_days_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="GoogleCalendarIntegration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("calendar_id", models.CharField(default="primary", max_length=180, verbose_name="agenda Google")),
                ("enabled", models.BooleanField(default=False, verbose_name="ativa")),
                ("sync_on_save", models.BooleanField(default=True, verbose_name="sincronizar novos agendamentos")),
                ("access_token", models.TextField(blank=True, verbose_name="access token")),
                ("refresh_token", models.TextField(blank=True, verbose_name="refresh token")),
                ("token_expires_at", models.DateTimeField(blank=True, null=True, verbose_name="token expira em")),
                ("connected_email", models.EmailField(blank=True, max_length=254, verbose_name="conta conectada")),
                ("last_sync_at", models.DateTimeField(blank=True, null=True, verbose_name="ultima sincronizacao")),
                ("last_error", models.TextField(blank=True, verbose_name="ultimo erro")),
            ],
            options={
                "verbose_name": "integracao Google Agenda",
                "verbose_name_plural": "integracoes Google Agenda",
            },
        ),
        migrations.CreateModel(
            name="WhatsAppIntegration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "provider",
                    models.CharField(
                        choices=[("meta", "Meta Cloud API"), ("twilio", "Twilio")],
                        default="meta",
                        max_length=20,
                        verbose_name="provedor",
                    ),
                ),
                ("enabled", models.BooleanField(default=False, verbose_name="ativa")),
                ("dry_run", models.BooleanField(default=True, verbose_name="modo teste")),
                ("default_country_code", models.CharField(default="55", max_length=4, verbose_name="codigo do pais")),
                ("phone_number_id", models.CharField(blank=True, max_length=80, verbose_name="ID do numero WhatsApp")),
                (
                    "business_account_id",
                    models.CharField(blank=True, max_length=80, verbose_name="ID da conta WhatsApp Business"),
                ),
                ("last_test_at", models.DateTimeField(blank=True, null=True, verbose_name="ultimo teste")),
                ("last_error", models.TextField(blank=True, verbose_name="ultimo erro")),
            ],
            options={
                "verbose_name": "integracao WhatsApp",
                "verbose_name_plural": "integracoes WhatsApp",
            },
        ),
    ]
