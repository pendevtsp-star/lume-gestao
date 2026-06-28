from django.core.management.base import BaseCommand

from accounts.models import UserProfile
from accounts.onboarding import create_patient_user
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
            onboarding = create_patient_user(patient)
            if not onboarding:
                self.stdout.write(f"[ignorado] {patient.full_name} ja possui usuario vinculado")
                continue
            user = onboarding["user"]
            delivery = onboarding["delivery"]
            if delivery["sent"]:
                self.stdout.write(self.style.SUCCESS(f"[ok] {patient.full_name}: {user.username} enviado por {delivery['method']}"))
            else:
                profile = UserProfile.objects.get(user=user)
                self.stdout.write(
                    self.style.WARNING(
                        (
                            f"[manual] {patient.full_name}: login {user.username}; "
                            f"senha temporaria {onboarding['temporary_password']}; "
                            f"erro: {profile.onboarding_delivery_error}"
                        )
                    )
                )

        action = "processado(s)" if commit else "encontrado(s)"
        self.stdout.write(self.style.SUCCESS(f"{total} paciente(s) {action}."))
