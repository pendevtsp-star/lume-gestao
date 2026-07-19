from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from billing.models import Charge, Membership, Payment, ServicePlan
from billing.services import membership_receivables_between
from core.integrations.whatsapp import format_whatsapp_currency, render_whatsapp_template
from core.models import (
    ClinicSettings,
    WhatsAppAutomationRule,
    WhatsAppAutomationSettings,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from patients.models import Patient, ProfessionalPatientAssignment
from patients.services import professional_ids_for_patient
from scheduling.models import Appointment, PatientNotification
from scheduling.services import (
    appointment_day_message,
    patient_allows_notification,
    notification_preferences_for,
    session_confirmation_message,
    upsert_patient_notification,
)
from team.models import Professional


def default_professional_for_patient(patient):
    if not patient:
        return None
    professional_ids = professional_ids_for_patient(patient)
    professional = Professional.objects.filter(pk__in=professional_ids, active=True).order_by("full_name").first()
    if professional:
        return professional
    assignment = (
        ProfessionalPatientAssignment.objects.select_related("professional")
        .filter(patient=patient, active=True)
        .order_by("created_at")
        .first()
    )
    return assignment.professional if assignment else None


def build_whatsapp_message_context(patient=None, professional=None, appointment=None, payment=None, charge=None):
    clinic_settings = ClinicSettings.load()
    patient = patient or getattr(appointment, "patient", None)
    if not patient and payment:
        patient = payment.patient or (payment.membership.patient if payment.membership_id else None)
    if not patient and charge:
        patient = charge.patient
    professional = professional or getattr(appointment, "professional", None) or default_professional_for_patient(patient)

    if appointment:
        appointment_date = timezone.localtime(appointment.starts_at).strftime("%d/%m/%Y")
        appointment_time = timezone.localtime(appointment.starts_at).strftime("%H:%M")
    else:
        appointment_date = (timezone.localdate() + timedelta(days=1)).strftime("%d/%m/%Y")
        appointment_time = "09:00"

    due_date = "-"
    amount = "-"
    if payment:
        due_date = payment.due_date.strftime("%d/%m/%Y")
        amount = format_whatsapp_currency(payment.amount)
    elif charge:
        due_date = charge.due_date.strftime("%d/%m/%Y")
        amount = format_whatsapp_currency(charge.amount)

    clinic_phone = clinic_settings.phone or WhatsAppIntegration.load().clinic_whatsapp_number or "-"
    return {
        "[Paciente]": patient.full_name if patient else "Paciente",
        "[Profissional]": professional.full_name if professional else clinic_settings.clinic_name,
        "[Data]": appointment_date,
        "[Horario]": appointment_time,
        "[Valor]": amount,
        "[DataVencimento]": due_date,
        "[Clinica]": clinic_settings.clinic_name,
        "[TelefoneClinica]": clinic_phone,
    }


def whatsapp_preview_context(template_type):
    sample_patient = Patient(full_name="Maria Clara", phone="11999990000")
    sample_professional = Professional(full_name="Dra. Helena", specialty=Professional.Specialty.PILATES)
    sample_date = timezone.localdate() + timedelta(days=1)
    sample_appointment = Appointment(
        patient=sample_patient,
        professional=sample_professional,
        starts_at=timezone.make_aware(datetime.combine(sample_date, time(9, 0))),
        ends_at=timezone.make_aware(datetime.combine(sample_date, time(10, 0))),
    )
    if template_type == WhatsAppMessageTemplate.TemplateType.CHARGE:
        plan = ServicePlan(name="Pilates", category=ServicePlan.Category.PILATES, monthly_price=0)
        membership = Membership(patient=sample_patient, plan=plan)
        sample_payment = Payment(membership=membership, due_date=timezone.localdate() + timedelta(days=5), amount="320.00")
        return build_whatsapp_message_context(payment=sample_payment, professional=sample_professional)
    if template_type == WhatsAppMessageTemplate.TemplateType.BIRTHDAY:
        return build_whatsapp_message_context(patient=sample_patient, professional=sample_professional)
    return build_whatsapp_message_context(appointment=sample_appointment)


def whatsapp_target_number(custom_number, patient=None):
    from core.integrations.http import IntegrationError

    if custom_number:
        return custom_number
    if patient and patient.phone:
        return patient.phone
    raise IntegrationError("O destinatario selecionado nao possui telefone cadastrado. Informe um numero manualmente.")


def _create_scheduled_log(
    *,
    integration,
    template,
    patient,
    appointment=None,
    payment=None,
    charge=None,
    scheduled_for=None,
    automation_key="",
    context_payment=None,
):
    rendered_message = render_whatsapp_template(
        template.body,
        build_whatsapp_message_context(
            patient=patient,
            appointment=appointment,
            payment=context_payment or payment,
            charge=charge,
        ),
    )
    try:
        with transaction.atomic():
            return WhatsAppMessageLog.objects.create(
                integration=integration,
                template=template,
                patient=patient,
                appointment=appointment,
                payment=payment,
                charge=charge,
                recipient_name=patient.full_name,
                recipient_number=patient.phone,
                rendered_message=rendered_message,
                status=WhatsAppMessageLog.Status.SCHEDULED,
                scheduled_for=scheduled_for,
                automation_key=automation_key,
            )
    except IntegrityError:
        if not automation_key:
            raise
        return (
            WhatsAppMessageLog.objects.filter(automation_key=automation_key)
            .exclude(status=WhatsAppMessageLog.Status.CANCELED)
            .order_by("-created_at")
            .first()
        )


def enqueue_automatic_whatsapp_messages(now=None, limit=100):
    now = now or timezone.now()
    local_now = timezone.localtime(now)
    settings = WhatsAppAutomationSettings.load()
    integration = WhatsAppIntegration.load()
    WhatsAppMessageTemplate.ensure_defaults()
    WhatsAppAutomationRule.ensure_defaults()
    created = {
        "appointment": 0,
        "appointment_day": 0,
        "birthday": 0,
        "membership_due": 0,
        "membership_overdue": 0,
        "charge_overdue": 0,
    }

    if not integration.is_connected:
        return created

    appointment_rules = (
        WhatsAppAutomationRule.objects.select_related("template")
        .filter(active=True, trigger=WhatsAppAutomationRule.Trigger.APPOINTMENT_BEFORE, template__active=True)
        .order_by("hours_before", "pk")
    )
    for rule in appointment_rules:
        reminder_start = now + timedelta(hours=rule.hours_before)
        reminder_end = reminder_start + timedelta(minutes=60)
        recovery_start = now + timedelta(minutes=10)
        kind = (
            PatientNotification.Kind.APPOINTMENT_DAY
            if rule.hours_before <= 3
            else PatientNotification.Kind.SESSION_CONFIRMATION
        )
        appointments = (
            Appointment.objects.select_related("patient", "professional")
            .filter(
                status=Appointment.Status.SCHEDULED,
                patient__phone__gt="",
            )
            .filter(
                Q(starts_at__gte=reminder_start, starts_at__lt=reminder_end)
                | Q(starts_at__gte=recovery_start, starts_at__lt=reminder_start)
            )
            .order_by("starts_at")[:limit]
        )
        for appointment in appointments:
            if not patient_allows_notification(appointment.patient, kind):
                continue
            if not notification_preferences_for(appointment.patient).whatsapp_enabled:
                continue
            automation_key = f"appointment-rule:{rule.pk}:{appointment.pk}"
            already_delivered = WhatsAppMessageLog.objects.filter(
                appointment=appointment,
                template=rule.template,
                status__in=[WhatsAppMessageLog.Status.SENT, WhatsAppMessageLog.Status.DRY_RUN],
            ).exists()
            if already_delivered:
                continue
            log = (
                WhatsAppMessageLog.objects.filter(automation_key=automation_key)
                .exclude(status=WhatsAppMessageLog.Status.CANCELED)
                .order_by("-created_at")
                .first()
            )
            if log and log.status in [
                WhatsAppMessageLog.Status.SENT,
                WhatsAppMessageLog.Status.DRY_RUN,
                WhatsAppMessageLog.Status.SCHEDULED,
            ]:
                continue
            if log and log.status == WhatsAppMessageLog.Status.FAILED:
                continue
            if not log:
                log = _create_scheduled_log(
                    integration=integration,
                    template=rule.template,
                    patient=appointment.patient,
                    appointment=appointment,
                    scheduled_for=now,
                    automation_key=automation_key,
                )
            upsert_patient_notification(
                patient=appointment.patient,
                appointment=appointment,
                kind=kind,
                channel=PatientNotification.Channel.WHATSAPP,
                due_at=now,
                message=(appointment_day_message(appointment) if kind == PatientNotification.Kind.APPOINTMENT_DAY else session_confirmation_message(appointment)),
                key_parts=[appointment.pk, "automation-rule", rule.pk],
                delivery_log=log,
            )
            if rule.hours_before <= 3:
                created["appointment_day"] += 1
            else:
                created["appointment"] += 1

    if settings.birthday_messages_enabled and local_now.time() >= settings.birthday_send_time:
        template = WhatsAppMessageTemplate.objects.get(template_type=WhatsAppMessageTemplate.TemplateType.BIRTHDAY)
        if template.active:
            today = local_now.date()
            patients = Patient.objects.filter(
                active=True,
                birth_date__month=today.month,
                birth_date__day=today.day,
                phone__gt="",
            ).order_by("full_name")[:limit]
            for patient in patients:
                automation_key = f"birthday:{patient.pk}:{today.isoformat()}"
                exists = WhatsAppMessageLog.objects.filter(automation_key=automation_key).exclude(
                    status=WhatsAppMessageLog.Status.CANCELED
                ).exists()
                if exists:
                    continue
                _create_scheduled_log(
                    integration=integration,
                    template=template,
                    patient=patient,
                    scheduled_for=now,
                    automation_key=automation_key,
                )
                created["birthday"] += 1

    charge_template = WhatsAppMessageTemplate.objects.get(template_type=WhatsAppMessageTemplate.TemplateType.CHARGE)
    if charge_template.active:
        today = local_now.date()
        due_dates = []
        if settings.membership_due_reminders_enabled:
            due_dates.append((today + timedelta(days=settings.membership_due_days_before), "membership_due"))
        if settings.membership_due_on_date:
            due_dates.append((today, "membership_due"))
        if settings.membership_overdue_enabled:
            due_dates.append((today - timedelta(days=settings.membership_overdue_days_after), "membership_overdue"))

        for due_date, counter_key in due_dates:
            payments = (
                Payment.objects.select_related("membership__patient")
                .filter(
                    status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
                    due_date=due_date,
                    membership__patient__active=True,
                    membership__patient__phone__gt="",
                )
                .order_by("due_date", "membership__patient__full_name")[:limit]
            )
            for payment in payments:
                patient = payment.membership.patient
                automation_key = f"payment:{payment.pk}:{counter_key}:{today.isoformat()}"
                exists = WhatsAppMessageLog.objects.filter(automation_key=automation_key).exclude(
                    status=WhatsAppMessageLog.Status.CANCELED
                ).exists()
                if exists:
                    continue
                _create_scheduled_log(
                    integration=integration,
                    template=charge_template,
                    patient=patient,
                    payment=payment,
                    scheduled_for=now,
                    automation_key=automation_key,
                )
                created[counter_key] += 1

            # Mensalidades ainda nao recebidas so ganham um Payment quando a
            # gestora confirma o recebimento. Mesmo assim, elas precisam entrar
            # na rotina de cobranca e usar os mesmos dados no texto enviado.
            receivables = membership_receivables_between(due_date, due_date, limit=limit)
            for receivable in receivables:
                patient = receivable.membership.patient
                if not patient.phone:
                    continue
                automation_key = (
                    f"membership-receivable:{receivable.membership.pk}:"
                    f"{receivable.reference_month.isoformat()}:{counter_key}"
                )
                exists = WhatsAppMessageLog.objects.filter(automation_key=automation_key).exclude(
                    status=WhatsAppMessageLog.Status.CANCELED
                ).exists()
                if exists:
                    continue
                context_payment = Payment(
                    patient=patient,
                    membership=receivable.membership,
                    item_type=Payment.ItemType.MEMBERSHIP,
                    description=receivable.membership.plan.name,
                    reference_month=receivable.reference_month,
                    due_date=receivable.due_date,
                    amount=receivable.amount,
                )
                _create_scheduled_log(
                    integration=integration,
                    template=charge_template,
                    patient=patient,
                    scheduled_for=now,
                    automation_key=automation_key,
                    context_payment=context_payment,
                )
                created[counter_key] += 1

        if settings.charge_overdue_enabled:
            charge_due_date = today - timedelta(days=settings.charge_overdue_days_after)
            charges = (
                Charge.objects.select_related("patient")
                .filter(
                    status__in=[Charge.Status.OPEN, Charge.Status.OVERDUE],
                    due_date=charge_due_date,
                    patient__active=True,
                    patient__phone__gt="",
                )
                .order_by("due_date", "patient__full_name")[:limit]
            )
            for charge in charges:
                patient = charge.patient
                automation_key = f"charge:{charge.pk}:charge_overdue:{today.isoformat()}"
                exists = WhatsAppMessageLog.objects.filter(automation_key=automation_key).exclude(
                    status=WhatsAppMessageLog.Status.CANCELED
                ).exists()
                if exists:
                    continue
                _create_scheduled_log(
                    integration=integration,
                    template=charge_template,
                    patient=patient,
                    charge=charge,
                    scheduled_for=now,
                    automation_key=automation_key,
                )
                created["charge_overdue"] += 1

    return created
