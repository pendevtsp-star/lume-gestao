from django.db.models import Q

from accounts.models import UserProfile
from accounts.permissions import get_profile
from patients.models import Patient, ProfessionalPatientAssignment


LINK_APPOINTMENT_STATUSES = ["requested", "scheduled", "completed", "no_show"]


def patient_ids_visible_to_professional(professional):
    """Return patient ids linked to an active professional by assignment or care."""
    from scheduling.models import Appointment

    if not professional or not professional.active:
        return Patient.objects.none().values_list("pk", flat=True)

    assignment_ids = ProfessionalPatientAssignment.objects.filter(
        professional=professional,
        professional__active=True,
        patient__active=True,
        active=True,
    ).values_list("patient_id", flat=True)
    appointment_ids = Appointment.objects.filter(
        professional=professional,
        professional__active=True,
        patient__active=True,
        status__in=LINK_APPOINTMENT_STATUSES,
    ).values_list("patient_id", flat=True)
    return Patient.objects.filter(Q(pk__in=assignment_ids) | Q(pk__in=appointment_ids)).values_list("pk", flat=True)


def patients_visible_to_user(user):
    """Return the canonical patient queryset visible to a clinic user."""
    queryset = Patient.objects.all()
    if user.is_superuser:
        return queryset

    profile = get_profile(user)
    if not profile:
        return queryset.none()
    if profile.role in {
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
        UserProfile.Role.VIEWER,
    }:
        return queryset
    if profile.is_patient and profile.patient_id:
        return queryset.filter(pk=profile.patient_id)
    if profile.is_professional and profile.professional_id:
        return queryset.filter(pk__in=patient_ids_visible_to_professional(profile.professional))
    return queryset.none()
