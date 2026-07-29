from django.db import migrations, models


FINANCIAL_TEMPLATE_TYPES = (
    ("membership_due", "Mensalidade a vencer"),
    ("membership_due_date", "Mensalidade no vencimento"),
    ("membership_overdue", "Mensalidade vencida"),
    ("charge_overdue", "Cobranca avulsa vencida"),
)


def copy_financial_templates(apps, schema_editor):
    Template = apps.get_model("core", "WhatsAppMessageTemplate")
    legacy = Template.objects.filter(template_type="charge").first()
    if not legacy:
        return
    for template_type, title in FINANCIAL_TEMPLATE_TYPES:
        Template.objects.get_or_create(
            template_type=template_type,
            defaults={
                "title": title,
                "description": legacy.description,
                "body": legacy.body,
                "meta_template_name": "",
                "meta_template_language": legacy.meta_template_language,
                "send_time": legacy.send_time,
                "active": legacy.active,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0017_whatsapp_delivery_policy")]

    operations = [
        migrations.AlterField(
            model_name="whatsappmessagetemplate",
            name="template_type",
            field=models.CharField(
                choices=[
                    ("appointment", "Mensagem de agendamento"),
                    ("session_soon", "Sessao proxima"),
                    ("charge", "Mensagem de cobranca"),
                    ("membership_due", "Mensalidade a vencer"),
                    ("membership_due_date", "Mensalidade no vencimento"),
                    ("membership_overdue", "Mensalidade vencida"),
                    ("charge_overdue", "Cobranca avulsa vencida"),
                    ("birthday", "Mensagem de aniversario"),
                    ("custom", "Modelo personalizado"),
                ],
                max_length=20,
                verbose_name="tipo",
            ),
        ),
        migrations.RunPython(
            copy_financial_templates,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
