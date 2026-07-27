from django.db.models import Q

from accounts.models import UserProfile
from accounts.permissions import get_profile
from patients.models import Patient
from scheduling.models import Appointment, ProfessionalAvailability
from scheduling.services import completion_needs_credit_adjustment


def appointments_for_user(user):
    queryset = Appointment.objects.select_related("patient", "professional", "series")
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
        return queryset.filter(patient=profile.patient)
    if profile.is_professional and profile.professional_id:
        return queryset.filter(professional=profile.professional)
    return queryset.none()


def visible_patient_ids_for_user(user):
    if user.is_superuser:
        return Patient.objects.values_list("pk", flat=True)
    profile = get_profile(user)
    if not profile:
        return Patient.objects.none().values_list("pk", flat=True)
    if profile.role in {
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
        UserProfile.Role.VIEWER,
    }:
        return Patient.objects.values_list("pk", flat=True)
    if profile.is_patient and profile.patient_id:
        return Patient.objects.filter(pk=profile.patient_id).values_list("pk", flat=True)
    if profile.is_professional and profile.professional_id:
        return (
            Patient.objects.filter(appointments__professional=profile.professional)
            .distinct()
            .values_list("pk", flat=True)
        )
    return Patient.objects.none().values_list("pk", flat=True)


def filter_appointment_search(queryset, query):
    if not query:
        return queryset
    return queryset.filter(
        Q(patient__full_name__icontains=query)
        | Q(professional__full_name__icontains=query)
        | Q(status__icontains=query)
        | Q(notes__icontains=query)
    )


def filter_availability_search(queryset, query):
    if not query:
        return queryset
    return queryset.filter(
        Q(professional__full_name__icontains=query) | Q(notes__icontains=query)
    )


def build_calendar_session_groups(appointments):
    grouped = {}
    for appointment in appointments:
        if appointment.slot_capacity > 1:
            key = (
                appointment.professional_id,
                appointment.starts_at,
                appointment.ends_at,
                appointment.slot_group or f"slot-{appointment.starts_at.isoformat()}",
            )
        else:
            key = ("appointment", appointment.pk)
        grouped.setdefault(key, []).append(appointment)

    sessions = []
    for group_appointments in grouped.values():
        group_appointments = sorted(
            group_appointments, key=lambda item: item.patient.full_name
        )
        first = group_appointments[0]
        capacity = max(appointment.slot_capacity for appointment in group_appointments)
        occupied = len(group_appointments)
        requested = any(
            appointment.status == Appointment.Status.REQUESTED
            for appointment in group_appointments
        )
        completed = all(
            appointment.status == Appointment.Status.COMPLETED
            for appointment in group_appointments
        )
        status_class = (
            Appointment.Status.REQUESTED
            if requested
            else Appointment.Status.COMPLETED
            if completed
            else first.status
        )
        patient_names = [appointment.patient.full_name for appointment in group_appointments]
        preview_names = patient_names[:2]
        sessions.append(
            {
                "appointment": first,
                "appointments": group_appointments,
                "starts_at": first.starts_at,
                "ends_at": first.ends_at,
                "professional": first.professional,
                "status_class": status_class,
                "status_display": (
                    "Solicitado"
                    if requested
                    else "Realizado"
                    if completed
                    else first.get_status_display()
                ),
                "is_group": capacity > 1,
                "is_recurring": any(
                    appointment.series_id for appointment in group_appointments
                ),
                "capacity": capacity,
                "occupied": occupied,
                "available": max(capacity - occupied, 0),
                "title": "Sessao em grupo" if capacity > 1 else first.patient.full_name,
                "patient_names": preview_names,
                "hidden_count": max(occupied - len(preview_names), 0),
            }
        )

    return sorted(
        sessions,
        key=lambda session: (session["starts_at"], session["professional"].full_name),
    )


def annotate_credit_adjustment_flags(appointments):
    for appointment in appointments:
        appointment.needs_credit_adjustment = completion_needs_credit_adjustment(
            appointment
        )
    return appointments


def availabilities_for_user(user):
    queryset = ProfessionalAvailability.objects.select_related("professional")
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
    if profile and profile.is_professional and profile.professional_id:
        return queryset.filter(professional=profile.professional)
    return queryset.none()
