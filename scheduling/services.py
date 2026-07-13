from datetime import datetime
from datetime import time
from datetime import timedelta

from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F

from billing.models import Membership, Payment
from core.models import ClinicSettings
from scheduling.models import Appointment
from scheduling.models import AppointmentAttendance
from scheduling.models import PatientAchievement
from scheduling.models import PatientGoal
from scheduling.models import PatientNotification
from scheduling.models import ServicePackage
from scheduling.models import ServicePackageAdjustment


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


def package_candidates_for_appointment(appointment, *, with_balance_only=False, lock=False):
    packages = ServicePackage.objects.filter(
        membership__patient=appointment.patient,
        status=ServicePackage.Status.ACTIVE,
    )
    if lock:
        packages = packages.select_for_update()
    if appointment.service_plan_id:
        packages = packages.filter(membership__plan_id=appointment.service_plan_id)
    if with_balance_only:
        packages = packages.filter(used_sessions__lt=F("total_sessions"))
    return packages.select_related("membership__patient", "membership__plan").order_by("expires_on", "created_at")


def completion_package_for_appointment(appointment, *, lock=False):
    packages = package_candidates_for_appointment(appointment, with_balance_only=True, lock=lock)
    if not appointment.service_plan_id and packages.values("membership__plan_id").distinct().count() > 1:
        raise ValidationError(
            "Este paciente possui mais de uma adesao ativa. Edite o agendamento e informe o plano/servico antes da baixa."
        )
    return packages.first()


def completion_needs_credit_adjustment(appointment):
    if appointment.status in {
        appointment.Status.COMPLETED,
        appointment.Status.CANCELED,
        appointment.Status.RESCHEDULED,
    }:
        return False
    if hasattr(appointment, "service_usage"):
        return False
    try:
        package = completion_package_for_appointment(appointment)
    except ValidationError:
        return False
    return not package or package.remaining_sessions < appointment.service_units


def membership_for_credit_adjustment(appointment):
    if appointment.service_plan_id:
        membership, _created = resolve_membership_for_plan(
            appointment.patient,
            appointment.service_plan,
            starts_on=timezone.localdate(),
        )
        return membership

    memberships = Membership.objects.filter(patient=appointment.patient, status=Membership.Status.ACTIVE).select_related("plan")
    if memberships.count() == 1:
        return memberships.first()
    raise ValidationError(
        "Informe o plano/servico no agendamento antes de adicionar credito automaticamente para este paciente."
    )


def ensure_credit_for_appointment(appointment, user):
    package = completion_package_for_appointment(appointment, lock=True)
    required_units = appointment.service_units
    if package and package.remaining_sessions >= required_units:
        return package

    missing_units = required_units
    if package:
        missing_units = required_units - package.remaining_sessions
        package.total_sessions += missing_units
        package.notes = append_note(package.notes, "Credito extra adicionado durante a baixa de atendimento.")
        package.full_clean()
        package.save(update_fields=["total_sessions", "notes", "updated_at"])
    else:
        membership = membership_for_credit_adjustment(appointment)
        package = ServicePackage(
            membership=membership,
            total_sessions=missing_units,
            used_sessions=0,
            starts_on=timezone.localdate(),
            status=ServicePackage.Status.ACTIVE,
            notes="Credito extra criado durante a baixa de atendimento.",
        )
        package.full_clean()
        package.save()

    adjustment = ServicePackageAdjustment(
        service_package=package,
        appointment=appointment,
        delta_sessions=missing_units,
        reason=ServicePackageAdjustment.Reason.APPOINTMENT_NO_CREDIT,
        notes="Ajuste confirmado pelo usuario durante a baixa de atendimento.",
        created_by=user,
    )
    adjustment.full_clean()
    adjustment.save()
    return package


def upsert_attendance(appointment, status, *, user=None, notes=""):
    attendance, _created = AppointmentAttendance.objects.update_or_create(
        appointment=appointment,
        defaults={
            "patient": appointment.patient,
            "professional": appointment.professional,
            "status": status,
            "registered_by": user,
            "registered_at": timezone.now(),
            "notes": notes,
        },
    )
    return attendance


def mark_absence(appointment, *, user=None, justified=False, notes=""):
    if appointment.status in {Appointment.Status.COMPLETED, Appointment.Status.RESCHEDULED, Appointment.Status.CANCELED}:
        raise ValidationError("Este agendamento nao pode receber falta.")
    appointment.status = Appointment.Status.NO_SHOW
    appointment.full_clean()
    appointment.save(update_fields=["status", "updated_at"])
    status = AppointmentAttendance.Status.JUSTIFIED_ABSENCE if justified else AppointmentAttendance.Status.ABSENT
    return upsert_attendance(appointment, status, user=user, notes=notes)


def record_attendance_for_completed_appointment(appointment, *, user=None, notes=""):
    attendance = upsert_attendance(
        appointment,
        AppointmentAttendance.Status.PRESENT,
        user=user,
        notes=notes,
    )
    maybe_create_attendance_achievement(appointment.patient, user=user)
    return attendance


def record_attendance_for_canceled_appointment(appointment, *, user=None, notes=""):
    return upsert_attendance(
        appointment,
        AppointmentAttendance.Status.CLINIC_CANCELED,
        user=user,
        notes=notes,
    )


def record_attendance_for_rescheduled_appointment(appointment, *, user=None, notes=""):
    return upsert_attendance(
        appointment,
        AppointmentAttendance.Status.RESCHEDULED,
        user=user,
        notes=notes,
    )


def maybe_create_attendance_achievement(patient, *, user=None):
    present_count = AppointmentAttendance.objects.filter(
        patient=patient,
        status=AppointmentAttendance.Status.PRESENT,
    ).count()
    if present_count and present_count % 8 == 0:
        title = f"{present_count} aulas realizadas"
        PatientAchievement.objects.get_or_create(
            patient=patient,
            title=title,
            defaults={
                "description": "Conquista criada automaticamente pelo historico de presenca.",
                "created_by": user,
            },
        )


def appointment_day_message(appointment):
    local_start = timezone.localtime(appointment.starts_at)
    return (
        f"Hoje tem aula: {appointment.patient.full_name} as {local_start:%H:%M} "
        f"com {appointment.professional.full_name}."
    )


def session_confirmation_message(appointment):
    local_start = timezone.localtime(appointment.starts_at)
    return (
        f"Confirmacao de sessao: {appointment.patient.full_name} tem aula em "
        f"{local_start:%d/%m as %H:%M}. Se precisar remarcar, avise a equipe com antecedencia."
    )


def absence_warning_message(appointment):
    return session_confirmation_message(appointment)


def renewal_message(payment):
    return (
        f"Renovacao do plano: {payment.patient_display} tem vencimento em "
        f"{payment.due_date:%d/%m/%Y} no valor de R$ {payment.amount}."
    )


def upsert_patient_notification(*, patient, kind, due_at, message, appointment=None, channel=None, key_parts=None):
    channel = channel or PatientNotification.Channel.PANEL
    key_parts = key_parts or []
    idempotency_key = ":".join([kind, str(patient.pk), *(str(part) for part in key_parts)])
    notification, created = PatientNotification.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "patient": patient,
            "appointment": appointment,
            "kind": kind,
            "channel": channel,
            "status": PatientNotification.Status.PENDING,
            "due_at": due_at,
            "message": message,
        },
    )
    return notification, created


def generate_operational_notifications(*, reference_date=None, days_ahead=1):
    reference_date = reference_date or timezone.localdate()
    created = {
        "appointment_day": 0,
        "session_confirmation": 0,
        "absence_warning": 0,
        "plan_renewal": 0,
    }
    today_start = timezone.make_aware(datetime.combine(reference_date, time.min))
    today_end = timezone.make_aware(datetime.combine(reference_date, time.max))
    tomorrow = reference_date + timedelta(days=days_ahead)
    tomorrow_start = timezone.make_aware(datetime.combine(tomorrow, time.min))
    tomorrow_end = timezone.make_aware(datetime.combine(tomorrow, time.max))

    for appointment in Appointment.objects.select_related("patient", "professional").filter(
        status__in=[Appointment.Status.SCHEDULED, Appointment.Status.REQUESTED],
        starts_at__gte=today_start,
        starts_at__lte=today_end,
    ):
        _notification, was_created = upsert_patient_notification(
            patient=appointment.patient,
            appointment=appointment,
            kind=PatientNotification.Kind.APPOINTMENT_DAY,
            due_at=appointment.starts_at,
            message=appointment_day_message(appointment),
            key_parts=[appointment.pk, reference_date.isoformat()],
        )
        if was_created:
            created["appointment_day"] += 1

    for appointment in Appointment.objects.select_related("patient", "professional").filter(
        status=Appointment.Status.SCHEDULED,
        starts_at__gte=tomorrow_start,
        starts_at__lte=tomorrow_end,
    ):
        _notification, was_created = upsert_patient_notification(
            patient=appointment.patient,
            appointment=appointment,
            kind=PatientNotification.Kind.SESSION_CONFIRMATION,
            channel=PatientNotification.Channel.WHATSAPP,
            due_at=appointment.starts_at - timedelta(hours=24),
            message=session_confirmation_message(appointment),
            key_parts=[appointment.pk, "session-confirmation"],
        )
        if was_created:
            created["session_confirmation"] += 1
            created["absence_warning"] += 1

    reminder_days = ClinicSettings.load().membership_due_reminder_days
    due_date = reference_date + timedelta(days=reminder_days)
    for payment in Payment.objects.select_related("patient", "membership__patient").filter(
        status=Payment.Status.PENDING,
        due_date=due_date,
    ):
        patient = payment.patient or payment.membership.patient
        _notification, was_created = upsert_patient_notification(
            patient=patient,
            kind=PatientNotification.Kind.PLAN_RENEWAL,
            due_at=timezone.make_aware(datetime.combine(reference_date, time(9, 0))),
            message=renewal_message(payment),
            key_parts=[payment.pk, due_date.isoformat()],
        )
        if was_created:
            created["plan_renewal"] += 1
    return created


def patient_monthly_summary(patient, *, reference_date=None):
    reference_date = reference_date or timezone.localdate()
    month_start = reference_date.replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    appointments = Appointment.objects.filter(patient=patient, starts_at__date__gte=month_start, starts_at__date__lt=next_month)
    attendance = AppointmentAttendance.objects.filter(patient=patient, appointment__starts_at__date__gte=month_start, appointment__starts_at__date__lt=next_month)
    scheduled = appointments.exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED]).count()
    present = attendance.filter(status=AppointmentAttendance.Status.PRESENT).count()
    absences = attendance.filter(
        status__in=[AppointmentAttendance.Status.ABSENT, AppointmentAttendance.Status.JUSTIFIED_ABSENCE]
    ).count()
    frequency = round((present / scheduled) * 100, 1) if scheduled else 0
    latest_checkin = patient.checkins.order_by("-created_at").first()
    return {
        "month_start": month_start,
        "scheduled": scheduled,
        "present": present,
        "absences": absences,
        "frequency": frequency,
        "active_goals": PatientGoal.objects.filter(patient=patient, status=PatientGoal.Status.ACTIVE).count(),
        "achievements": patient.achievements.filter(achieved_on__gte=month_start, achieved_on__lt=next_month).count(),
        "latest_checkin": latest_checkin,
    }
