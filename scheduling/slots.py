from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from scheduling.models import Appointment, ProfessionalAvailability


ACTIVE_APPOINTMENT_STATUSES = [Appointment.Status.REQUESTED, Appointment.Status.SCHEDULED]


def make_local_datetime(day, value):
    return timezone.make_aware(datetime.combine(day, value), timezone.get_current_timezone())


def active_appointments_for_slot(
    professional_id,
    starts_at,
    ends_at,
    exclude_appointment_id=None,
    exclude_appointment_ids=None,
):
    queryset = Appointment.objects.filter(
        professional_id=professional_id,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    exclude_ids = set(exclude_appointment_ids or [])
    if exclude_appointment_id:
        exclude_ids.add(exclude_appointment_id)
    if exclude_ids:
        queryset = queryset.exclude(pk__in=exclude_ids)
    return queryset


def slot_capacity_snapshot(
    professional_id,
    starts_at,
    ends_at,
    exclude_appointment_id=None,
    exclude_appointment_ids=None,
):
    overlaps = active_appointments_for_slot(
        professional_id,
        starts_at,
        ends_at,
        exclude_appointment_id=exclude_appointment_id,
        exclude_appointment_ids=exclude_appointment_ids,
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


def slot_availability_snapshot(
    professional,
    starts_at,
    ends_at,
    *,
    exclude_appointment_id=None,
    exclude_appointment_ids=None,
    incoming_count=1,
):
    """Return the single capacity decision used by the agenda and confirmation flows."""
    if not professional or not starts_at or not ends_at or ends_at <= starts_at:
        return {
            "partial_overlap": False,
            "exact_count": 0,
            "existing_capacity": 0,
            "availability_capacity": 1,
            "capacity": 1,
            "remaining_capacity": 0,
            "slot_group": "",
            "availability_matches": False,
            "is_available": False,
        }

    snapshot = slot_capacity_snapshot(
        professional.pk,
        starts_at,
        ends_at,
        exclude_appointment_id=exclude_appointment_id,
        exclude_appointment_ids=exclude_appointment_ids,
    )
    availability_capacity = availability_capacity_for_slot(professional, starts_at, ends_at)
    capacity = max(snapshot["existing_capacity"], availability_capacity)
    remaining_capacity = max(capacity - snapshot["exact_count"], 0)
    availability_matches = ProfessionalAvailability.objects.slot_available(
        professional_id=professional.pk,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    can_join_existing_group = existing_group_slot_has_capacity(snapshot, incoming_count=incoming_count)

    return {
        **snapshot,
        "availability_capacity": availability_capacity,
        "capacity": capacity,
        "remaining_capacity": remaining_capacity,
        "availability_matches": availability_matches,
        "is_available": (
            not snapshot["partial_overlap"]
            and (availability_matches or can_join_existing_group)
            and remaining_capacity >= max(incoming_count, 1)
        ),
    }


def existing_group_slot_has_capacity(snapshot, *, incoming_count=1):
    return (
        snapshot["existing_capacity"] > 1
        and not snapshot["partial_overlap"]
        and snapshot["remaining_capacity"] >= max(incoming_count, 1)
    )


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


def slot_is_available(professional, starts_at, ends_at, exclude_appointment=None, incoming_count=1):
    snapshot = slot_availability_snapshot(
        professional,
        starts_at,
        ends_at,
        exclude_appointment_id=getattr(exclude_appointment, "pk", None),
        incoming_count=incoming_count,
    )
    return snapshot["is_available"]


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

    def add_slot(starts_at, ends_at, snapshot):
        if starts_at in seen or not snapshot["is_available"]:
            return
        seen.add(starts_at)
        local_start = timezone.localtime(starts_at)
        local_end = timezone.localtime(ends_at)
        slots.append(
            {
                "starts_at": starts_at,
                "ends_at": ends_at,
                "start_value": local_start.strftime("%H:%M"),
                "label": f"{local_start:%H:%M} - {local_end:%H:%M}",
                "capacity": snapshot["capacity"],
                "occupied": snapshot["exact_count"],
                "remaining_capacity": snapshot["remaining_capacity"],
                "group_slot": snapshot["existing_capacity"] > 0,
            }
        )

    for window in windows:
        cursor = make_local_datetime(day, window.starts_at)
        window_end = make_local_datetime(day, window.ends_at)
        while cursor + duration <= window_end:
            starts_at = cursor
            ends_at = cursor + duration
            snapshot = slot_availability_snapshot(
                professional,
                starts_at,
                ends_at,
                exclude_appointment_id=getattr(exclude_appointment, "pk", None),
            )
            add_slot(starts_at, ends_at, snapshot)
            cursor += duration

    day_start = make_local_datetime(day, time.min)
    day_end = day_start + timedelta(days=1)
    existing_group_slots = (
        Appointment.objects.filter(
            professional=professional,
            status__in=ACTIVE_APPOINTMENT_STATUSES,
            starts_at__gte=day_start,
            starts_at__lt=day_end,
            slot_capacity__gt=1,
        )
        .order_by("starts_at", "ends_at")
        .values_list("starts_at", "ends_at")
        .distinct()
    )
    for starts_at, ends_at in existing_group_slots:
        if ends_at - starts_at != duration:
            continue
        snapshot = slot_availability_snapshot(
            professional,
            starts_at,
            ends_at,
            exclude_appointment_id=getattr(exclude_appointment, "pk", None),
        )
        add_slot(starts_at, ends_at, snapshot)

    return sorted(slots, key=lambda slot: slot["starts_at"])
