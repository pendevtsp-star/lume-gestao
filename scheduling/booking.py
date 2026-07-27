from datetime import timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError

from scheduling.forms import AppointmentSlotSearchForm
from scheduling.models import Appointment, AppointmentSeries
from scheduling.slots import (
    existing_group_slot_has_capacity,
    make_local_datetime,
    slot_availability_snapshot,
)


ACTIVE_APPOINTMENT_STATUSES = [
    Appointment.Status.REQUESTED,
    Appointment.Status.SCHEDULED,
]


def recurrence_dates_from_form(form):
    first_date = form.cleaned_data["appointment_date"]
    if form.cleaned_data.get("repeat_mode") != AppointmentSlotSearchForm.RepeatMode.WEEKLY:
        return [first_date]

    dates = [first_date]
    interval = form.cleaned_data.get("repeat_interval_weeks") or 1
    repeat_until = form.cleaned_data.get("repeat_until")
    repeat_count = form.cleaned_data.get("repeat_count")
    current = first_date
    while True:
        if repeat_count and len(dates) >= repeat_count:
            break
        current += timedelta(weeks=interval)
        if repeat_until and current > repeat_until:
            break
        dates.append(current)
        if not repeat_until and repeat_count and len(dates) >= repeat_count:
            break
    return dates


def create_series_for_dates(dates, form, user):
    if len(dates) <= 1:
        return None
    interval = form.cleaned_data.get("repeat_interval_weeks") or 1
    repeat_until = form.cleaned_data.get("repeat_until") or dates[-1]
    return AppointmentSeries.objects.create(
        created_by=user,
        repeat_type=AppointmentSeries.RepeatType.WEEKLY,
        interval_weeks=interval,
        repeat_until=repeat_until,
        occurrences_count=len(dates),
        notes=f"Serie semanal criada a partir de {dates[0]:%d/%m/%Y}",
    )


def has_future_series_appointments(appointment):
    if not appointment.series_id:
        return False
    return appointment.series.appointments.filter(
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        starts_at__gt=appointment.starts_at,
    ).exists()


def duplicate_appointments_exist(
    patient_ids, professional, starts_at, ends_at, exclude_ids=None
):
    queryset = Appointment.objects.filter(
        patient_id__in=patient_ids,
        professional=professional,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    if exclude_ids:
        queryset = queryset.exclude(pk__in=exclude_ids)
    return queryset.exists()


def build_occurrence_payloads(
    *,
    professional,
    patient_ids,
    dates,
    selected_start,
    duration_minutes,
    requested_capacity,
    exclude_ids_by_date=None,
):
    payloads = []
    duration = timedelta(minutes=duration_minutes)
    requested_capacity = max(requested_capacity or 1, len(patient_ids))
    exclude_ids_by_date = exclude_ids_by_date or {}

    for current_date in dates:
        starts_at = make_local_datetime(current_date, selected_start)
        ends_at = starts_at + duration
        exclude_ids = exclude_ids_by_date.get(current_date.isoformat(), [])
        snapshot = slot_availability_snapshot(
            professional,
            starts_at,
            ends_at,
            exclude_appointment_ids=exclude_ids,
            incoming_count=len(patient_ids),
        )
        if snapshot["partial_overlap"]:
            raise ValidationError(
                f"{current_date:%d/%m/%Y}: o profissional ja possui atendimento nesse horario."
            )
        joins_existing_group = existing_group_slot_has_capacity(
            snapshot, incoming_count=len(patient_ids)
        )
        if not snapshot["availability_matches"] and not joins_existing_group:
            raise ValidationError(
                f"{current_date:%d/%m/%Y}: horario fora da disponibilidade recorrente."
            )
        if duplicate_appointments_exist(
            patient_ids, professional, starts_at, ends_at, exclude_ids=exclude_ids
        ):
            raise ValidationError(
                f"{current_date:%d/%m/%Y}: ao menos um paciente ja possui este horario."
            )

        slot_capacity = (
            snapshot["existing_capacity"]
            if joins_existing_group and not snapshot["availability_matches"]
            else max(snapshot["capacity"], requested_capacity)
        )
        if snapshot["exact_count"] + len(patient_ids) > slot_capacity:
            raise ValidationError(
                f"{current_date:%d/%m/%Y}: capacidade da sessao excedida para este horario."
            )
        payloads.append(
            {
                "date": current_date,
                "starts_at": starts_at,
                "ends_at": ends_at,
                "slot_capacity": slot_capacity,
                "slot_group": snapshot["slot_group"]
                or (uuid4().hex if slot_capacity > 1 else ""),
            }
        )
    return payloads
