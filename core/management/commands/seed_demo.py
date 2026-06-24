from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import Membership, Payment, ServicePlan
from patients.models import Patient
from team.models import Employee, Professional


def add_months(base_date, offset):
    month_index = base_date.month - 1 + offset
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


class Command(BaseCommand):
    help = "Cria dados demonstrativos para desenvolvimento local."

    def handle(self, *args, **options):
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@lume.local", "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password("Lume@12345")
            user.save(update_fields=["password"])

        patients = [
            ("Marina Alves", "11987654321", "marina@example.com", "12345678901"),
            ("Camila Rocha", "11966554433", "camila@example.com", "12345678902"),
            ("Renata Lima", "11955443322", "renata@example.com", "12345678903"),
            ("Bianca Costa", "11944332211", "bianca@example.com", None),
        ]
        patient_objects = []
        for name, phone, email, cpf in patients:
            patient, _ = Patient.objects.update_or_create(
                full_name=name,
                defaults={
                    "phone": phone,
                    "email": email,
                    "cpf": cpf,
                    "emergency_contact": "Contato familiar",
                    "clinical_notes": "Cadastro demonstrativo. Revisar anamnese antes do atendimento.",
                    "active": True,
                },
            )
            patient_objects.append(patient)

        Employee.objects.update_or_create(
            full_name="Sofia Martins",
            defaults={"role": Employee.Role.RECEPTION, "phone": "11911112222", "email": "sofia@lume.local"},
        )
        Employee.objects.update_or_create(
            full_name="Lucas Ferraz",
            defaults={"role": Employee.Role.FINANCE, "phone": "11933334444", "email": "lucas@lume.local"},
        )

        Professional.objects.update_or_create(
            full_name="Dra. Helena Prado",
            defaults={
                "specialty": Professional.Specialty.PHYSIOTHERAPY,
                "registration_number": "CREFITO-12345",
                "phone": "11988887777",
                "email": "helena@lume.local",
            },
        )
        Professional.objects.update_or_create(
            full_name="Laura Menezes",
            defaults={
                "specialty": Professional.Specialty.PILATES,
                "registration_number": "PIL-2026",
                "phone": "11977776666",
                "email": "laura@lume.local",
            },
        )

        pilates, _ = ServicePlan.objects.update_or_create(
            name="Pilates 2x por semana",
            defaults={
                "category": ServicePlan.Category.PILATES,
                "monthly_price": Decimal("420.00"),
                "sessions_per_week": 2,
                "description": "Plano mensal de pilates em turma reduzida.",
                "active": True,
            },
        )
        fisio, _ = ServicePlan.objects.update_or_create(
            name="Fisioterapia mensal",
            defaults={
                "category": ServicePlan.Category.PHYSIOTHERAPY,
                "monthly_price": Decimal("560.00"),
                "sessions_per_week": 2,
                "description": "Acompanhamento fisioterapeutico recorrente.",
                "active": True,
            },
        )
        combo, _ = ServicePlan.objects.update_or_create(
            name="Pilates + Fisioterapia",
            defaults={
                "category": ServicePlan.Category.COMBO,
                "monthly_price": Decimal("760.00"),
                "sessions_per_week": 3,
                "description": "Combinacao para pacientes com rotina de reabilitacao.",
                "active": True,
            },
        )

        memberships = [
            (patient_objects[0], pilates, 10, Decimal("0.00")),
            (patient_objects[1], fisio, 8, Decimal("40.00")),
            (patient_objects[2], combo, 15, Decimal("60.00")),
        ]
        membership_objects = []
        for patient, plan, due_day, discount in memberships:
            membership, _ = Membership.objects.update_or_create(
                patient=patient,
                status=Membership.Status.ACTIVE,
                defaults={
                    "plan": plan,
                    "due_day": due_day,
                    "discount_amount": discount,
                    "start_date": timezone.localdate().replace(day=1),
                },
            )
            membership_objects.append(membership)

        current_month = timezone.localdate().replace(day=1)
        payment_payloads = [
            (membership_objects[0], add_months(current_month, 0), Payment.Status.PENDING, None),
            (membership_objects[1], add_months(current_month, 0), Payment.Status.PAID, timezone.localdate()),
            (membership_objects[2], add_months(current_month, -1), Payment.Status.OVERDUE, None),
        ]
        for membership, reference, status, paid_at in payment_payloads:
            Payment.objects.update_or_create(
                membership=membership,
                reference_month=reference,
                defaults={
                    "due_date": date(reference.year, reference.month, membership.due_day),
                    "amount": membership.monthly_amount,
                    "status": status,
                    "method": Payment.Method.MANUAL,
                    "paid_at": paid_at,
                },
            )

        self.stdout.write(self.style.SUCCESS("Dados demonstrativos criados. Usuario: admin | Senha: Lume@12345"))
