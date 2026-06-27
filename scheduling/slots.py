from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from scheduling.models import Appointment, ProfessionalAvailability


ACTIVE_APPOINTMENT_STATUSES = [Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED]


def make_local_datetime(day, value):
    return timezone.make_aware(datetime.combine(day, value), timezone.get_current_timezone())


def active_appointments_for_slot(professional_id, starts_at, ends_at, exclude_appointment_id=None):
    queryset = Appointment.objects.filter(
        professional_id=professional_id,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    if exclude_appointment_id:
        queryset = queryset.exclude(pk=exclude_appointment_id)
    return queryset


def slot_capacity_snapshot(professional_id, starts_at, ends_at, exclude_appointment_id=None):
    overlaps = active_appointments_for_slot(
        professional_id,
        starts_at,
        ends_at,
        exclude_appointment_id=exclude_appointment_id,
    )
    partial_overlaps = overlaps.exclude(starts_at=starts_at, ends_at=ends_at)
    exact_overlaps = overlaps.filter(starts_at=starts_at, ends_at=ends_at)
    active_count = exact_overlaps.count()
    existing_capacity = max((appointment.slot_capacity for appointment in exact_overlaps), default=0)

    return {
        "partial_overlap": partial_overlaps.exists(),
        "exact_count": active_count,
        "existing_capacity": existing_capacity,
        "remaining_capacity": max(existing_capacity - active_count, 0),
        "slot_group": next((appointment.slot_group for appointment in exact_overlaps if appointment.slot_group), ""),
    }


def availability_capacity_for_slot(professional, starts_at, ends_at):
    if not professional or not starts_at or not ends_at:
        return 1
    local_start = timezone.localtime(starts_at)
    local_end = timezone.localtime(ends_at)
    window = (
        ProfessionalAvailability.objects.filter(
            professional=professional,
            active=True,
            weekday=local_start.weekday(),
            valid_from__lte=local_start.date(),
            starts_at__lte=local_start.time(),
            ends_at__gte=local_end.time(),
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=local_start.date()))
        .order_by("-session_capacity", "starts_at")
        .first()
    )
    return window.session_capacity if window else 1


def appointment_overlaps(professional_id, starts_at, ends_at, exclude_appointment_id=None):
    snapshot = slot_capacity_snapshot(
        professional_id,
        starts_at,
        ends_at,
        exclude_appointment_id=exclude_appointment_id,
    )
    if snapshot["partial_overlap"]:
        return True
    return snapshot["existing_capacity"] > 0 and snapshot["remaining_capacity"] <= 0


def slot_is_available(professional, starts_at, ends_at, exclude_appointment=None):
    if not professional or not starts_at or not ends_at:
        return False
    if ends_at <= starts_at:
        return False
    snapshot = slot_capacity_snapshot(
        professional.pk,
        starts_at,
        ends_at,
        exclude_appointment_id=getattr(exclude_appointment, "pk", None),
    )
    if snapshot["partial_overlap"]:
        return False
    if snapshot["existing_capacity"] > 0 and snapshot["remaining_capacity"] <= 0:
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
            snapshot = slot_capacity_snapshot(
                professional.pk,
                starts_at,
                ends_at,
                exclude_appointment_id=getattr(exclude_appointment, "pk", None),
            )
            if (
                starts_at not in seen
                and not snapshot["partial_overlap"]
                and (snapshot["existing_capacity"] == 0 or snapshot["remaining_capacity"] > 0)
            ):
                seen.add(starts_at)
                local_start = timezone.localtime(starts_at)
                local_end = timezone.localtime(ends_at)
                slot_capacity = snapshot["existing_capacity"] or window.session_capacity
                occupied = snapshot["exact_count"]
                remaining = slot_capacity - occupied if snapshot["existing_capacity"] else window.session_capacity
                slots.append(
                    {
                        "starts_at": starts_at,
                        "ends_at": ends_at,
                        "start_value": local_start.strftime("%H:%M"),
                        "label": f"{local_start:%H:%M} - {local_end:%H:%M}",
                        "capacity": slot_capacity,
                        "occupied": occupied,
                        "remaining_capacity": remaining,
                        "group_slot": snapshot["existing_capacity"] > 0,
                    }
                )
            cursor += duration

    return sorted(slots, key=lambda slot: slot["starts_at"])
