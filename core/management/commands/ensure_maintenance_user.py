from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string
from decouple import config

from accounts.models import UserProfile


class Command(BaseCommand):
    help = "Cria ou valida o usuario tecnico de manutencao quando habilitado por variavel de ambiente."

    def handle(self, *args, **options):
        enabled = config("LUME_MAINTENANCE_USER_ENABLED", default=False, cast=bool)
        if not enabled:
            self.stdout.write("Usuario tecnico de manutencao desabilitado.")
            return

        username = config("LUME_MAINTENANCE_USERNAME", default="root").strip()
        password = config("LUME_MAINTENANCE_PASSWORD", default="").strip()
        rotate_password = config("LUME_MAINTENANCE_ROTATE_PASSWORD", default=False, cast=bool)

        if not username:
            raise CommandError("LUME_MAINTENANCE_USERNAME nao pode ficar vazio.")
        if not password:
            generated_hint = get_random_string(32)
            raise CommandError(
                "Defina LUME_MAINTENANCE_PASSWORD no .env antes de habilitar o usuario tecnico. "
                f"Exemplo de senha forte: {generated_hint}"
            )

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@lume.local",
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        should_set_password = created or rotate_password
        if should_set_password:
            try:
                validate_password(password, user)
            except ValidationError as error:
                raise CommandError("; ".join(error.messages)) from error
            user.set_password(password)

        changed_fields = []
        for field, value in {
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
        }.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed_fields.append(field)

        update_fields = changed_fields[:]
        if should_set_password:
            update_fields.append("password")
        if update_fields:
            user.save(update_fields=update_fields)

        UserProfile.objects.update_or_create(
            user=user,
            defaults={"role": UserProfile.Role.MANAGEMENT},
        )

        action = "criado" if created else "validado"
        self.stdout.write(self.style.SUCCESS(f"Usuario tecnico '{username}' {action} com perfil de gerencia."))
