from django.core.management.base import BaseCommand, CommandError

from accounts.onboarding import ensure_patient_user
from patients.models import Patient


class Command(BaseCommand):
    help = "Cria usuarios de primeiro acesso para pacientes que ainda nao possuem login."

    def add_arguments(self, parser):
        parser.add_argument("--send", action="store_true", help="Envia credenciais por e-mail ou WhatsApp quando possivel.")
        parser.add_argument(
            "--show-passwords",
            action="store_true",
            help="Mostra a senha temporaria no terminal para entrega manual.",
        )
        parser.add_argument("--limit", type=int, help="Limita a quantidade de pacientes processados.")

    def handle(self, *args, **options):
        send = options["send"]
        show_passwords = options["show_passwords"]
        limit = options.get("limit")

        if not send and not show_passwords:
            raise CommandError(
                "Use --send ou --show-passwords. Sem uma dessas opcoes, a senha temporaria seria criada sem entrega."
            )

        queryset = (
            Patient.objects.filter(active=True, user_profile__isnull=True)
            .order_by("full_name", "id")
        )
        if limit:
            queryset = queryset[:limit]

        created_count = 0
        skipped_count = 0
        for patient in queryset:
            result = ensure_patient_user(patient, send_notifications=send)
            if not result.created:
                skipped_count += 1
                continue

            created_count += 1
            status = result.delivery_channel or "sem envio"
            line = f"[{patient.id}] {patient.full_name} -> login {result.username} ({status})"
            if show_passwords:
                line = f"{line} | senha temporaria: {result.temporary_password}"
            if result.delivery_error:
                line = f"{line} | aviso: {result.delivery_error}"
            self.stdout.write(line)

        self.stdout.write(self.style.SUCCESS(f"Usuarios criados: {created_count}. Ignorados: {skipped_count}."))
