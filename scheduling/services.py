from django.utils import timezone

from billing.models import Membership
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
