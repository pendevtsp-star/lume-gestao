from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_userprofile_whatsapp"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("patient", "Paciente"),
                    ("professional", "Profissional"),
                    ("administration", "Administracao"),
                    ("management", "Gerencia"),
                    ("viewer", "Visualizacao"),
                ],
                default="administration",
                max_length=30,
                verbose_name="perfil",
            ),
        ),
    ]
