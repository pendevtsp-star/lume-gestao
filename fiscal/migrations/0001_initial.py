import decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("billing", "0003_expense_categories"),
        ("patients", "0005_professionalnote_structured_data_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="FiscalSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "provider",
                    models.CharField(
                        choices=[
                            ("manual", "Prefeitura/manual"),
                            ("nacional", "NFS-e Nacional"),
                            ("focus_nfe", "Focus NFe"),
                            ("plugnotas", "PlugNotas"),
                            ("nfe_io", "NFE.io"),
                            ("tecnospeed", "TecnoSpeed"),
                        ],
                        default="manual",
                        max_length=30,
                        verbose_name="provedor",
                    ),
                ),
                (
                    "environment",
                    models.CharField(
                        choices=[("sandbox", "Teste"), ("production", "Producao")],
                        default="sandbox",
                        max_length=20,
                        verbose_name="ambiente",
                    ),
                ),
                ("municipality", models.CharField(blank=True, max_length=120, verbose_name="municipio de emissao")),
                ("cnpj", models.CharField(blank=True, max_length=18, verbose_name="CNPJ da clinica")),
                (
                    "municipal_registration",
                    models.CharField(blank=True, max_length=40, verbose_name="inscricao municipal"),
                ),
                ("tax_regime", models.CharField(blank=True, max_length=80, verbose_name="regime tributario")),
                (
                    "default_service_code",
                    models.CharField(blank=True, max_length=30, verbose_name="codigo de servico padrao"),
                ),
                (
                    "default_iss_rate",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        max_digits=5,
                        verbose_name="ISS padrao (%)",
                    ),
                ),
                ("api_key", models.CharField(blank=True, max_length=255, verbose_name="token/chave da integracao")),
                ("nfse_enabled", models.BooleanField(default=False, verbose_name="habilitar emissao de NFS-e")),
                ("last_status", models.CharField(blank=True, max_length=180, verbose_name="ultimo status")),
                ("last_error", models.TextField(blank=True, verbose_name="ultimo erro")),
            ],
            options={
                "verbose_name": "configuracao fiscal",
                "verbose_name_plural": "configuracoes fiscais",
            },
        ),
        migrations.CreateModel(
            name="FiscalDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "document_type",
                    models.CharField(
                        choices=[("nfse", "NFS-e"), ("receipt", "Cupom/recibo interno")],
                        default="nfse",
                        max_length=20,
                        verbose_name="tipo",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Rascunho"),
                            ("issued", "Emitida/registrada"),
                            ("sent", "Enviada"),
                            ("canceled", "Cancelada"),
                            ("failed", "Falhou"),
                        ],
                        default="draft",
                        max_length=20,
                        verbose_name="status",
                    ),
                ),
                ("issue_date", models.DateField(default=django.utils.timezone.localdate, verbose_name="data de emissao")),
                ("description", models.CharField(max_length=220, verbose_name="descricao do servico")),
                ("service_code", models.CharField(blank=True, max_length=30, verbose_name="codigo de servico")),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))],
                        verbose_name="valor do servico",
                    ),
                ),
                (
                    "iss_rate",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        max_digits=5,
                        verbose_name="ISS (%)",
                    ),
                ),
                (
                    "iss_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        editable=False,
                        max_digits=10,
                        verbose_name="valor ISS",
                    ),
                ),
                (
                    "total_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("0.00"),
                        editable=False,
                        max_digits=10,
                        verbose_name="valor total",
                    ),
                ),
                ("customer_name", models.CharField(max_length=180, verbose_name="nome do tomador")),
                ("customer_document", models.CharField(blank=True, max_length=18, verbose_name="CPF/CNPJ do tomador")),
                ("customer_email", models.EmailField(blank=True, max_length=254, verbose_name="e-mail do tomador")),
                ("customer_phone", models.CharField(blank=True, max_length=30, verbose_name="WhatsApp do tomador")),
                ("external_id", models.CharField(blank=True, max_length=80, verbose_name="numero/referencia externa")),
                (
                    "verification_code",
                    models.CharField(blank=True, max_length=80, verbose_name="codigo de verificacao"),
                ),
                ("provider_payload", models.JSONField(blank=True, default=dict, verbose_name="retorno do provedor")),
                ("notes", models.TextField(blank=True, verbose_name="observacoes")),
                (
                    "charge",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fiscal_documents",
                        to="billing.charge",
                        verbose_name="cobranca",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fiscal_documents",
                        to="patients.patient",
                        verbose_name="paciente",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fiscal_documents",
                        to="billing.payment",
                        verbose_name="pagamento",
                    ),
                ),
            ],
            options={
                "verbose_name": "documento fiscal",
                "verbose_name_plural": "documentos fiscais",
                "ordering": ["-issue_date", "-created_at"],
            },
        ),
    ]
