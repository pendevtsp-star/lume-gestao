from django.utils import timezone

from billing.models import Membership, Payment
from core.models import ClinicSettings
from scheduling.models import ServicePackage


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
