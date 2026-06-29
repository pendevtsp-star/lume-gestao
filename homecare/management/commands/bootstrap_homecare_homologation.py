from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from homecare.models import HomecareCategory
from homecare.models import HomecarePlan
from homecare.models import HomecareSubscription
from patients.models import Patient


class Command(BaseCommand):
    help = "Prepara dados minimos do modulo Fisioterapia em Casa para homologacao segura."

    def add_arguments(self, parser):
        parser.add_argument("--patient-id", type=int, help="ID do paciente que recebera acesso manual.")
        parser.add_argument("--patient-email", help="E-mail do paciente que recebera acesso manual.")
        parser.add_argument("--access-days", type=int, default=30, help="Dias de acesso manual para homologacao.")

    def handle(self, *args, **options):
        if not settings.HOMECARE_ENABLED or not settings.HOMECARE_INTERNAL_ENABLED:
            raise CommandError("Ative HOMECARE_ENABLED=True e HOMECARE_INTERNAL_ENABLED=True para homologacao interna.")

        categories = [
            ("pilates-em-casa", "Pilates em casa", "Aulas gerais de pilates para rotina domiciliar.", 10),
            ("mobilidade", "Mobilidade", "Exercicios de mobilidade e consciencia corporal.", 20),
            ("fortalecimento", "Fortalecimento", "Sequencias leves de fortalecimento e estabilidade.", 30),
            ("alongamento", "Alongamento", "Alongamentos guiados para cuidado complementar.", 40),
        ]
        created_categories = 0
        for slug, name, description, order in categories:
            _, created = HomecareCategory.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": description,
                    "display_order": order,
                    "active": True,
                },
            )
            created_categories += int(created)

        plan, plan_created = HomecarePlan.objects.update_or_create(
            slug="pilates-em-casa-mensal",
            defaults={
                "name": "Pilates em Casa - Mensal",
                "description": "Acesso mensal a biblioteca de videos da clinica.",
                "monthly_price": Decimal("49.90"),
                "billing_cycle": HomecarePlan.BillingCycle.MONTHLY,
                "display_order": 10,
                "active": True,
                "public_checkout_enabled": False,
            },
        )

        patient = self.get_patient(options)
        subscription = None
        if patient:
            now = timezone.now()
            subscription = (
                HomecareSubscription.objects.filter(
                    patient=patient,
                    plan=plan,
                    source=HomecareSubscription.Source.MANUAL,
                )
                .order_by("-created_at")
                .first()
            )
            if not subscription:
                subscription = HomecareSubscription(patient=patient, plan=plan, source=HomecareSubscription.Source.MANUAL)
            subscription.status = HomecareSubscription.Status.ACTIVE
            subscription.provider = HomecareSubscription.Provider.MANUAL
            subscription.starts_at = subscription.starts_at or now
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=options["access_days"])
            subscription.notes = "Acesso manual criado para homologacao do modulo Fisioterapia em Casa."
            subscription.save()

        self.stdout.write(self.style.SUCCESS("Homologacao Fisioterapia em Casa preparada."))
        self.stdout.write(f"Categorias criadas: {created_categories}.")
        self.stdout.write(f"Plano {'criado' if plan_created else 'atualizado'}: {plan.name}.")
        if subscription:
            self.stdout.write(f"Acesso manual liberado para paciente #{patient.pk}: {patient.full_name}.")
        else:
            self.stdout.write("Nenhum paciente recebeu acesso. Informe --patient-id ou --patient-email para liberar manualmente.")

    def get_patient(self, options):
        patient_id = options.get("patient_id")
        patient_email = (options.get("patient_email") or "").strip()
        if patient_id:
            return Patient.objects.get(pk=patient_id)
        if patient_email:
            return Patient.objects.get(email__iexact=patient_email)
        return None
