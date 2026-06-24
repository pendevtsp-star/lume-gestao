from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from scheduling.models import Appointment, ProfessionalAvailability


ACTIVE_APPOINTMENT_STATUSES = [Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED]


def make_local_datetime(day, value):
    return timezone.make_aware(datetime.combine(day, value), timezone.get_current_timezone())


def appointment_overlaps(professional_id, starts_at, ends_at, exclude_appointment_id=None):
    queryset = Appointment.objects.filter(
        professional_id=professional_id,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    if exclude_appointment_id:
        queryset = queryset.exclude(pk=exclude_appointment_id)
    return queryset.exists()


def slot_is_available(professional, starts_at, ends_at, exclude_appointment=None):
    if not professional or not starts_at or not ends_at:
        return False
    if ends_at <= starts_at:
        return False
    if appointment_overlaps(
        professional.pk,
        starts_at,
        ends_at,
        exclude_appointment_id=getattr(exclude_appointment, "pk", None),
    ):
        return False
    return ProfessionalAvailability.objects.slot_available(
        professional_id=professional.pk,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def generate_available_slots(professional, day, duration_minutes, exclude_appointment=None):
    if not professional or not day or not duration_minutes:
        return []

    duration = timedelta(minutes=int(duration_minutes))
    windows = (
        ProfessionalAvailability.objects.filter(
            professional=professional,
            active=True,
            weekday=day.weekday(),
            valid_from__lte=day,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=day))
        .order_by("starts_at")
    )
    slots = []
    seen = set()
    for window in windows:
        cursor = make_local_datetime(day, window.starts_at)
        window_end = make_local_datetime(day, window.ends_at)
        while cursor + duration <= window_end:
            starts_at = cursor
            ends_at = cursor + duration
            if starts_at not in seen and not appointment_overlaps(
                professional.pk,
                starts_at,
                ends_at,
                exclude_appointment_id=getattr(exclude_appointment, "pk", None),
            ):
                seen.add(starts_at)
                local_start = timezone.localtime(starts_at)
                local_end = timezone.localtime(ends_at)
                slots.append(
                    {
                        "starts_at": starts_at,
                        "ends_at": ends_at,
                        "start_value": local_start.strftime("%H:%M"),
                        "label": f"{local_start:%H:%M} - {local_end:%H:%M}",
                    }
                )
            cursor += duration

    return sorted(slots, key=lambda slot: slot["starts_at"])
