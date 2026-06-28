from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_userprofile_viewer_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="must_change_password",
            field=models.BooleanField(default=False, verbose_name="trocar senha no proximo acesso"),
        ),
    ]
