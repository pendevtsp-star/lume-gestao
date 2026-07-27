from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from billing.models import Payment
from scheduling.models import (
    AppointmentAttendance,
    PatientAchievement,
    PatientCheckIn,
    PatientGoal,
)


ZERO = Decimal("0.00")
ONE_DECIMAL = Decimal("0.1")


def as_decimal(value):
    if value in (None, ""):
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def sum_total(queryset, field="amount"):
    return queryset.aggregate(total=Sum(field))["total"] or ZERO


def percent(value, total):
    total_decimal = as_decimal(total)
    if total_decimal <= 0:
        return ZERO
    return (as_decimal(value) * Decimal("100") / total_decimal).quantize(
        ONE_DECIMAL,
        rounding=ROUND_HALF_UP,
    )


def percent_int(value, total):
    if not total:
        return 0
    return int(percent(value, total).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def shift_month(day, delta):
    month_index = day.month - 1 + delta
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def month_last_day(day):
    return date(day.year, day.month, monthrange(day.year, day.month)[1])


def coerce_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def prettify_value(value):
    if value in (None, ""):
        return "-"
    if isinstance(value, bool):
        return "Sim" if value else "Nao"
    if isinstance(value, list):
        rendered = ", ".join(prettify_value(item) for item in value if item not in (None, ""))
        return rendered or "-"
    if isinstance(value, dict):
        rendered = ", ".join(f"{key}: {prettify_value(item)}" for key, item in value.items())
        return rendered or "-"
    return str(value)


def br_percent(value):
    return f"{value}%".replace(".", ",")


def br_date(value):
    if isinstance(value, str):
        parsed = coerce_date(value)
        if parsed:
            return parsed.strftime("%d/%m/%Y")
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else str(value)


def monthly_patient_snapshot(patient, start, end):
    attendance = AppointmentAttendance.objects.filter(
        patient=patient,
        appointment__starts_at__date__range=(start, end),
    ).select_related("appointment", "professional")
    counts = {
        status: attendance.filter(status=status).count()
        for status, _ in AppointmentAttendance.Status.choices
    }
    attended = counts[AppointmentAttendance.Status.PRESENT] + counts[AppointmentAttendance.Status.REPLACEMENT]
    absences = counts[AppointmentAttendance.Status.ABSENT]
    justified = counts[AppointmentAttendance.Status.JUSTIFIED_ABSENCE]
    eligible = attended + absences + justified
    checkins = PatientCheckIn.objects.filter(
        patient=patient,
        created_at__date__range=(start, end),
    ).order_by("created_at")
    pain_values = [item.pain_level for item in checkins if item.pain_level is not None]
    active_goals = PatientGoal.objects.filter(patient=patient, status=PatientGoal.Status.ACTIVE)
    overdue_goals = active_goals.filter(target_date__lt=timezone.localdate())
    achievements = PatientAchievement.objects.filter(patient=patient, achieved_on__range=(start, end))
    payments = Payment.objects.filter(patient=patient, due_date__range=(start, end))
    pending_payments = payments.filter(status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE])
    latest_checkin = checkins.last()
    return {
        "patient": patient,
        "attendance": attendance,
        "attended": attended,
        "absences": absences,
        "justified": justified,
        "rescheduled": counts[AppointmentAttendance.Status.RESCHEDULED],
        "frequency": percent(attended, eligible),
        "checkins": checkins,
        "checkin_count": checkins.count(),
        "pain_average": (sum(pain_values) / len(pain_values)) if pain_values else None,
        "pain_first": pain_values[0] if pain_values else None,
        "pain_latest": pain_values[-1] if pain_values else None,
        "latest_checkin": latest_checkin,
        "active_goals": active_goals,
        "overdue_goals": overdue_goals,
        "achievements": achievements,
        "payments": payments,
        "pending_payments": pending_payments,
    }
