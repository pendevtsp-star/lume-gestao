from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from billing.models import Charge, Membership, Payment
from core.models import WhatsAppMessageLog
from scheduling.models import Appointment, PatientNotificationPreference


RETRY_DELAYS_MINUTES = (2, 5, 15)


@dataclass(frozen=True)
class DeliveryDecision:
    allowed: bool
    terminal_status: str | None
    reason_code: str
    user_message: str


def _blocked(status, reason_code, user_message):
    return DeliveryDecision(
        allowed=False,
        terminal_status=status,
        reason_code=reason_code,
        user_message=user_message,
    )


def _purpose_expiry_reason(log):
    if log.message_purpose in {
        WhatsAppMessageLog.MessagePurpose.APPOINTMENT_CONFIRMATION,
        WhatsAppMessageLog.MessagePurpose.APPOINTMENT_SOON,
    } or log.appointment_id:
        return (
            "appointment_started",
            "Esta mensagem nao foi enviada porque o horario da sessao ja passou.",
        )
    if log.message_purpose == WhatsAppMessageLog.MessagePurpose.BIRTHDAY:
        return (
            "birthday_date_passed",
            "Esta mensagem nao foi enviada porque a data do aniversario ja passou.",
        )
    return (
        "validity_expired",
        "Esta mensagem nao foi enviada porque o prazo terminou.",
    )


def _appointment_decision(log, now):
    appointment = log.appointment
    if not appointment:
        return _blocked(
            WhatsAppMessageLog.Status.EXPIRED,
            "appointment_missing",
            "Esta mensagem nao foi enviada porque o agendamento nao existe mais.",
        )
    status_reasons = {
        Appointment.Status.CANCELED: (
            "appointment_canceled",
            "Esta mensagem nao foi enviada porque a sessao foi cancelada.",
        ),
        Appointment.Status.RESCHEDULED: (
            "appointment_rescheduled",
            "Esta mensagem nao foi enviada porque a sessao foi reagendada.",
        ),
        Appointment.Status.COMPLETED: (
            "appointment_completed",
            "Esta mensagem nao foi enviada porque a sessao ja foi concluida.",
        ),
        Appointment.Status.NO_SHOW: (
            "appointment_closed",
            "Esta mensagem nao foi enviada porque a sessao ja foi encerrada.",
        ),
    }
    if appointment.status in status_reasons:
        reason, message = status_reasons[appointment.status]
        return _blocked(WhatsAppMessageLog.Status.EXPIRED, reason, message)
    if appointment.status != Appointment.Status.SCHEDULED:
        return _blocked(
            WhatsAppMessageLog.Status.EXPIRED,
            "appointment_not_scheduled",
            "Esta mensagem nao foi enviada porque a sessao nao esta agendada.",
        )
    if log.expires_at and appointment.starts_at != log.expires_at:
        return _blocked(
            WhatsAppMessageLog.Status.EXPIRED,
            "appointment_rescheduled",
            "Esta mensagem nao foi enviada porque o horario da sessao mudou.",
        )
    if appointment.starts_at <= now:
        return _blocked(
            WhatsAppMessageLog.Status.EXPIRED,
            "appointment_started",
            "Esta mensagem nao foi enviada porque o horario da sessao ja passou.",
        )
    return None


def _membership_receivable_is_open(log):
    parts = (log.automation_key or "").split(":")
    if len(parts) != 4 or parts[0] != "membership-receivable":
        return True
    try:
        membership_id = int(parts[1])
        reference_month = datetime.fromisoformat(parts[2]).date()
    except (TypeError, ValueError):
        return False
    membership = Membership.objects.filter(pk=membership_id).first()
    if not membership or membership.status != Membership.Status.ACTIVE:
        return False
    payment = Payment.objects.filter(
        membership_id=membership_id,
        reference_month=reference_month,
    ).first()
    return not payment or payment.status in {
        Payment.Status.PENDING,
        Payment.Status.OVERDUE,
    }


def evaluate_delivery(log, *, now: datetime) -> DeliveryDecision:
    if timezone.is_naive(now):
        raise ValueError("now deve possuir fuso horario.")

    if log.expires_at and now >= log.expires_at:
        reason, message = _purpose_expiry_reason(log)
        return _blocked(WhatsAppMessageLog.Status.EXPIRED, reason, message)

    patient = log.patient
    if not patient and log.message_purpose != WhatsAppMessageLog.MessagePurpose.MANUAL:
        return _blocked(
            WhatsAppMessageLog.Status.FAILED,
            "patient_missing",
            "Esta mensagem nao foi enviada porque o paciente nao existe mais.",
        )
    if patient and not patient.active:
        return _blocked(
            WhatsAppMessageLog.Status.EXPIRED,
            "patient_inactive",
            "Esta mensagem nao foi enviada porque o paciente esta inativo.",
        )
    if not (log.recipient_number or "").strip() or (
        patient and not (patient.phone or "").strip()
    ):
        return _blocked(
            WhatsAppMessageLog.Status.FAILED,
            "phone_missing",
            "Esta mensagem nao foi enviada porque o paciente nao possui telefone.",
        )

    preferences = (
        PatientNotificationPreference.objects.filter(patient=patient).first()
        if patient
        else None
    )
    if preferences and not preferences.whatsapp_enabled:
        return _blocked(
            WhatsAppMessageLog.Status.EXPIRED,
            "whatsapp_opt_out",
            "Esta mensagem nao foi enviada porque o paciente desativou avisos por WhatsApp.",
        )

    if (
        log.appointment_id
        or (
            log.message_purpose == WhatsAppMessageLog.MessagePurpose.MANUAL
            and log.expires_at
        )
        or log.message_purpose
        in {
            WhatsAppMessageLog.MessagePurpose.APPOINTMENT_CONFIRMATION,
            WhatsAppMessageLog.MessagePurpose.APPOINTMENT_SOON,
        }
    ):
        appointment_decision = _appointment_decision(log, now)
        if appointment_decision:
            return appointment_decision
        if preferences and not preferences.appointment_enabled:
            return _blocked(
                WhatsAppMessageLog.Status.EXPIRED,
                "appointment_notifications_disabled",
                "Esta mensagem nao foi enviada porque avisos de agenda estao desativados.",
            )

    if log.message_purpose == WhatsAppMessageLog.MessagePurpose.BIRTHDAY:
        local_today = timezone.localtime(now).date()
        birth_date = patient.birth_date
        if not birth_date or (birth_date.month, birth_date.day) != (local_today.month, local_today.day):
            return _blocked(
                WhatsAppMessageLog.Status.EXPIRED,
                "birthday_date_passed",
                "Esta mensagem nao foi enviada porque hoje nao e o aniversario do paciente.",
            )

    if log.payment_id or log.message_purpose in {
        WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_DUE,
        WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_OVERDUE,
    }:
        if preferences and not preferences.financial_enabled:
            return _blocked(
                WhatsAppMessageLog.Status.EXPIRED,
                "financial_notifications_disabled",
                "Esta mensagem nao foi enviada porque avisos financeiros estao desativados.",
            )
        if log.payment_id and log.payment.status not in {
            Payment.Status.PENDING,
            Payment.Status.OVERDUE,
        }:
            return _blocked(
                WhatsAppMessageLog.Status.EXPIRED,
                "payment_settled",
                "Esta mensagem nao foi enviada porque a mensalidade ja foi resolvida.",
            )
        if (
            not log.payment_id
            and log.message_purpose
            in {
                WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_DUE,
                WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_OVERDUE,
            }
            and not _membership_receivable_is_open(log)
        ):
            return _blocked(
                WhatsAppMessageLog.Status.EXPIRED,
                "payment_settled",
                "Esta mensagem nao foi enviada porque a mensalidade ja foi resolvida.",
            )

    if log.charge_id or log.message_purpose == WhatsAppMessageLog.MessagePurpose.CHARGE_OVERDUE:
        if preferences and not preferences.financial_enabled:
            return _blocked(
                WhatsAppMessageLog.Status.EXPIRED,
                "financial_notifications_disabled",
                "Esta mensagem nao foi enviada porque avisos financeiros estao desativados.",
            )
        if not log.charge_id:
            return _blocked(
                WhatsAppMessageLog.Status.EXPIRED,
                "charge_missing",
                "Esta mensagem nao foi enviada porque a cobranca nao existe mais.",
            )
        if log.charge.status not in {Charge.Status.OPEN, Charge.Status.OVERDUE}:
            return _blocked(
                WhatsAppMessageLog.Status.EXPIRED,
                "charge_settled",
                "Esta mensagem nao foi enviada porque a cobranca ja foi resolvida.",
            )

    return DeliveryDecision(
        allowed=True,
        terminal_status=None,
        reason_code="eligible",
        user_message="Mensagem elegivel para envio.",
    )


def calculate_next_retry(
    log,
    *,
    now: datetime,
    retryable: bool,
    delivery_uncertain: bool = False,
) -> datetime | None:
    if delivery_uncertain:
        return None
    if not retryable:
        return None
    if log.retry_policy == WhatsAppMessageLog.RetryPolicy.NONE:
        return None
    if log.attempt_count >= log.max_attempts:
        return None
    delay_index = min(max(log.attempt_count - 1, 0), len(RETRY_DELAYS_MINUTES) - 1)
    retry_at = now + timedelta(minutes=RETRY_DELAYS_MINUTES[delay_index])
    if log.expires_at and retry_at >= log.expires_at:
        return None
    if not evaluate_delivery(log, now=retry_at).allowed:
        return None
    return retry_at


def can_retry_manually(log, *, now: datetime) -> DeliveryDecision:
    if log.status == WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN:
        return _blocked(
            WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN,
            "delivery_uncertain",
            "Esta mensagem nao foi reenviada porque a entrega anterior e incerta.",
        )
    if log.status == WhatsAppMessageLog.Status.EXPIRED:
        return _blocked(
            WhatsAppMessageLog.Status.EXPIRED,
            log.terminal_reason or "validity_expired",
            "Esta mensagem nao foi reenviada porque o prazo terminou.",
        )
    if log.status in {
        WhatsAppMessageLog.Status.SENT,
        WhatsAppMessageLog.Status.DRY_RUN,
        WhatsAppMessageLog.Status.CANCELED,
    }:
        return _blocked(
            log.status,
            "terminal_status",
            "Esta mensagem nao pode ser reenviada neste estado.",
        )
    return evaluate_delivery(log, now=now)
