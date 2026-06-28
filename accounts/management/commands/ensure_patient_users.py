from django.core.management.base import BaseCommand

from accounts.onboarding import ensure_patient_user
from patients.models import Patient


class Command(BaseCommand):
    help = "Cria usuarios de primeiro acesso para pacientes ativos que ainda nao possuem login vinculado."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true", help="Cria os usuarios de verdade. Sem isso, apenas simula.")
        parser.add_argument("--limit", type=int, default=0, help="Limite opcional de pacientes processados.")

    def handle(self, *args, **options):
        commit = options["commit"]
        limit = options["limit"]
        queryset = Patient.objects.filter(active=True).exclude(user_profile__isnull=False).order_by("full_name")
        if limit:
            queryset = queryset[:limit]

        total = 0
        for patient in queryset:
            total += 1
            if not commit:
                self.stdout.write(f"[simulacao] criaria usuario para {patient.full_name}")
                continue
            result = ensure_patient_user(patient, send_notifications=True)
            if not result.created:
                self.stdout.write(f"[ignorado] {patient.full_name} ja possui usuario vinculado")
                continue
            if result.delivered:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[ok] {patient.full_name}: {result.username} enviado por {result.delivery_channel}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        (
                            f"[manual] {patient.full_name}: login {result.username}; "
                            f"senha temporaria {result.temporary_password}; "
                            f"erro: {result.delivery_error or 'sem canal de envio'}"
                        )
                    )
                )

        action = "processado(s)" if commit else "encontrado(s)"
        self.stdout.write(self.style.SUCCESS(f"{total} paciente(s) {action}."))
