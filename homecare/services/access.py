from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from accounts.models import UserProfile
from accounts.permissions import get_profile
from billing.models import Membership, Payment
from homecare.models import HomecareSubscription
from scheduling.models import ServicePackage


HOMECARE_STAFF_ACCESS_ROLES = {
    UserProfile.Role.PROFESSIONAL,
    UserProfile.Role.ADMINISTRATION,
    UserProfile.Role.MANAGEMENT,
    UserProfile.Role.VIEWER,
}


@dataclass(frozen=True)
class HomecareAccessResult:
    allowed: bool
    subscription: HomecareSubscription | None = None
    included_access: bool = False
    source: str = ""


def active_subscription_for_user(user):
    profile = get_profile(user)
    if not profile or not profile.is_patient or not profile.patient_id:
        return None
    if not profile.patient.active:
        return None
    now = timezone.now()
    return (
        HomecareSubscription.objects.select_related("plan", "patient")
        .filter(
            patient=profile.patient,
            status__in=[HomecareSubscription.Status.ACTIVE, HomecareSubscription.Status.TRIALING],
        )
        .filter(current_period_end__isnull=True)
        .first()
        or HomecareSubscription.objects.select_related("plan", "patient")
        .filter(
            patient=profile.patient,
            status__in=[HomecareSubscription.Status.ACTIVE, HomecareSubscription.Status.TRIALING],
            current_period_end__gte=now,
        )
        .order_by("-current_period_end")
        .first()
    )


def staff_has_homecare_access(user, profile=None):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    profile = profile or get_profile(user)
    return bool(profile and profile.role in HOMECARE_STAFF_ACCESS_ROLES)


def patient_has_homecare_plan_access(patient, today=None):
    if not patient or not patient.active:
        return False
    today = today or timezone.localdate()
    memberships = Membership.objects.select_related("plan").filter(
        patient=patient,
        status=Membership.Status.ACTIVE,
        plan__active=True,
        plan__grants_homecare_access=True,
    )
    for membership in memberships:
        if membership_has_overdue_payment(membership):
            continue
        packages = ServicePackage.objects.filter(membership=membership)
        if not packages.exists():
            return True
        if packages.filter(status=ServicePackage.Status.ACTIVE).filter(
            Q(expires_on__isnull=True) | Q(expires_on__gte=today)
        ).exists():
            return True
    return False


def membership_has_overdue_payment(membership):
    return Payment.objects.filter(membership=membership, status=Payment.Status.OVERDUE).exists()


def included_homecare_access_for_user(user):
    if not user.is_authenticated or not user.is_active:
        return False
    profile = get_profile(user)
    if not profile:
        return bool(user.is_superuser)
    if profile.is_patient:
        return bool(profile.patient_id and patient_has_homecare_plan_access(profile.patient))
    return staff_has_homecare_access(user, profile=profile)


def homecare_access_for_user(user):
    if not user.is_authenticated or not user.is_active:
        return HomecareAccessResult(allowed=False, source="anonymous")
    if staff_has_homecare_access(user):
        return HomecareAccessResult(allowed=True, included_access=True, source="staff")
    subscription = active_subscription_for_user(user)
    if subscription:
        return HomecareAccessResult(allowed=True, subscription=subscription, source="subscription")
    if included_homecare_access_for_user(user):
        return HomecareAccessResult(allowed=True, included_access=True, source="service_plan")
    return HomecareAccessResult(allowed=False, source="no_access")
