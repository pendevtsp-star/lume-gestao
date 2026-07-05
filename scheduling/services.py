from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F

from billing.models import Membership, Payment
from core.models import ClinicSettings
from scheduling.models import ServicePackage, ServicePackageAdjustment


def resolve_membership_for_plan(patient, plan, starts_on=None):
    clinic_settings = ClinicSettings.load()
    membership, created = Membership.objects.get_or_create(
        patient=patient,
        plan=plan,
        status=Membership.Status.ACTIVE,
        defaults={
            "due_day": clinic_settings.default_membership_due_day,
            "start_date": starts_on or timezone.localdate(),
        },
    )
    return membership, created


def package_defaults_for_plan(plan, starts_on=None):
    starts_on = starts_on or timezone.localdate()
    return {
        "total_sessions": plan.default_total_sessions,
        "expires_on": plan.default_expires_on(starts_on),
    }


def create_service_package_for_plan(patient, plan, starts_on=None, notes="", status=ServicePackage.Status.ACTIVE):
    starts_on = starts_on or timezone.localdate()
    membership, _created = resolve_membership_for_plan(patient, plan, starts_on=starts_on)
    defaults = package_defaults_for_plan(plan, starts_on)
    package = ServicePackage(
        membership=membership,
        total_sessions=defaults["total_sessions"],
        used_sessions=0,
        starts_on=starts_on,
        expires_on=defaults["expires_on"],
        status=status,
        notes=notes,
    )
    package.full_clean()
    package.save()
    return package


def cycle_reference_month(starts_on):
    return starts_on.replace(day=1)


def cycle_due_date(membership, starts_on):
    day = min(membership.due_day, 28)
    return starts_on.replace(day=day)


def register_membership_cycle_payment(
    membership,
    *,
    starts_on=None,
    mode="pending",
    method=Payment.Method.PIX,
    paid_at=None,
    notes="",
):
    starts_on = starts_on or timezone.localdate()
    paid_at = paid_at or timezone.localdate()
    status = Payment.Status.PAID if mode == "paid_now" else Payment.Status.PENDING
    reference_month = cycle_reference_month(starts_on)
    payment, _created = Payment.objects.get_or_create(
        membership=membership,
        reference_month=reference_month,
        defaults={
            "patient": membership.patient,
            "item_type": Payment.ItemType.MEMBERSHIP,
            "description": membership.plan.name,
            "due_date": paid_at if status == Payment.Status.PAID else cycle_due_date(membership, starts_on),
            "amount": membership.monthly_amount,
        },
    )
    payment.patient = membership.patient
    payment.item_type = Payment.ItemType.MEMBERSHIP
    payment.description = payment.description or membership.plan.name
    payment.status = status
    payment.method = method
    payment.amount = membership.monthly_amount
    payment.due_date = paid_at if status == Payment.Status.PAID else cycle_due_date(membership, starts_on)
    payment.paid_at = paid_at if status == Payment.Status.PAID else None
    payment.notes = append_note(payment.notes, notes)
    payment.full_clean()
    payment.save()
    return payment


def append_note(current_notes, new_note):
    new_note = (new_note or "").strip()
    if not new_note:
        return current_notes
    return f"{current_notes}\n{new_note}".strip() if current_notes else new_note


def package_candidates_for_appointment(appointment, *, with_balance_only=False, lock=False):
    packages = ServicePackage.objects.filter(
        membership__patient=appointment.patient,
        status=ServicePackage.Status.ACTIVE,
    )
    if lock:
        packages = packages.select_for_update()
    if appointment.service_plan_id:
        packages = packages.filter(membership__plan_id=appointment.service_plan_id)
    if with_balance_only:
        packages = packages.filter(used_sessions__lt=F("total_sessions"))
    return packages.select_related("membership__patient", "membership__plan").order_by("expires_on", "created_at")


def completion_package_for_appointment(appointment, *, lock=False):
    packages = package_candidates_for_appointment(appointment, with_balance_only=True, lock=lock)
    if not appointment.service_plan_id and packages.values("membership__plan_id").distinct().count() > 1:
        raise ValidationError(
            "Este paciente possui mais de uma adesao ativa. Edite o agendamento e informe o plano/servico antes da baixa."
        )
    return packages.first()


def completion_needs_credit_adjustment(appointment):
    if appointment.status in {
        appointment.Status.COMPLETED,
        appointment.Status.CANCELED,
        appointment.Status.RESCHEDULED,
    }:
        return False
    if hasattr(appointment, "service_usage"):
        return False
    try:
        package = completion_package_for_appointment(appointment)
    except ValidationError:
        return False
    return not package or package.remaining_sessions < appointment.service_units


def membership_for_credit_adjustment(appointment):
    if appointment.service_plan_id:
        membership, _created = resolve_membership_for_plan(
            appointment.patient,
            appointment.service_plan,
            starts_on=timezone.localdate(),
        )
        return membership

    memberships = Membership.objects.filter(patient=appointment.patient, status=Membership.Status.ACTIVE).select_related("plan")
    if memberships.count() == 1:
        return memberships.first()
    raise ValidationError(
        "Informe o plano/servico no agendamento antes de adicionar credito automaticamente para este paciente."
    )


def ensure_credit_for_appointment(appointment, user):
    package = completion_package_for_appointment(appointment, lock=True)
    required_units = appointment.service_units
    if package and package.remaining_sessions >= required_units:
        return package

    missing_units = required_units
    if package:
        missing_units = required_units - package.remaining_sessions
        package.total_sessions += missing_units
        package.notes = append_note(package.notes, "Credito extra adicionado durante a baixa de atendimento.")
        package.full_clean()
        package.save(update_fields=["total_sessions", "notes", "updated_at"])
    else:
        membership = membership_for_credit_adjustment(appointment)
        package = ServicePackage(
            membership=membership,
            total_sessions=missing_units,
            used_sessions=0,
            starts_on=timezone.localdate(),
            status=ServicePackage.Status.ACTIVE,
            notes="Credito extra criado durante a baixa de atendimento.",
        )
        package.full_clean()
        package.save()

    adjustment = ServicePackageAdjustment(
        service_package=package,
        appointment=appointment,
        delta_sessions=missing_units,
        reason=ServicePackageAdjustment.Reason.APPOINTMENT_NO_CREDIT,
        notes="Ajuste confirmado pelo usuario durante a baixa de atendimento.",
        created_by=user,
    )
    adjustment.full_clean()
    adjustment.save()
    return package
