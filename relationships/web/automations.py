from dataclasses import dataclass
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from billing.models import Charge, Payment
from core.forms import RelationshipAutomationForm
from core.models import (
    WhatsAppAutomationRule,
    WhatsAppAutomationSettings,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from core.services.whatsapp_configuration import render_template_preview
from patients.models import Patient
from relationships.web.common import RelationshipAccessMixin
from scheduling.models import Appointment


@dataclass(frozen=True)
class AutomationDefinition:
    key: str
    title: str
    description: str
    enabled_field: str
    template_type: str
    purpose: str
    timing_field: str = ""
    timing_kind: str = "none"
    timing_label: str = ""
    timing_copy: str = ""


AUTOMATIONS = (
    AutomationDefinition(
        "appointment_confirmation",
        "Confirmação da sessão",
        "Lembra a paciente com antecedência e respeita qualquer mudança na agenda.",
        "appointment_reminders_enabled",
        WhatsAppMessageTemplate.TemplateType.APPOINTMENT,
        WhatsAppMessageLog.MessagePurpose.APPOINTMENT_CONFIRMATION,
        "appointment_reminder_hours_before",
        "hours",
        "Horas antes da sessão",
        "{value} horas antes",
    ),
    AutomationDefinition(
        "appointment_soon",
        "Sessão próxima",
        "Envia um aviso curto perto do início, nunca depois do horário marcado.",
        "appointment_day_reminders_enabled",
        WhatsAppMessageTemplate.TemplateType.SESSION_SOON,
        WhatsAppMessageLog.MessagePurpose.APPOINTMENT_SOON,
        "appointment_day_reminder_hours_before",
        "hours",
        "Horas antes da sessão",
        "{value} horas antes",
    ),
    AutomationDefinition(
        "birthday",
        "Aniversário",
        "Parabeniza pacientes ativos somente no dia do aniversário.",
        "birthday_messages_enabled",
        WhatsAppMessageTemplate.TemplateType.BIRTHDAY,
        WhatsAppMessageLog.MessagePurpose.BIRTHDAY,
        "birthday_send_time",
        "time",
        "",
        "às {value}",
    ),
    AutomationDefinition(
        "membership_due",
        "Mensalidade a vencer",
        "Avisa antes do vencimento enquanto a mensalidade continuar pendente.",
        "membership_due_reminders_enabled",
        WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE,
        WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_DUE,
        "membership_due_days_before",
        "days",
        "Dias antes do vencimento",
        "{value} dias antes",
    ),
    AutomationDefinition(
        "membership_due_date",
        "Mensalidade no vencimento",
        "Reforça o aviso no próprio dia, somente se ainda houver valor pendente.",
        "membership_due_on_date",
        WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_DUE_DATE,
        WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_DUE,
        timing_copy="no dia do vencimento",
    ),
    AutomationDefinition(
        "membership_overdue",
        "Mensalidade vencida",
        "Avisa após o vencimento e para automaticamente quando houver pagamento.",
        "membership_overdue_enabled",
        WhatsAppMessageTemplate.TemplateType.MEMBERSHIP_OVERDUE,
        WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_OVERDUE,
        "membership_overdue_days_after",
        "days",
        "Dias depois do vencimento",
        "{value} dias depois",
    ),
    AutomationDefinition(
        "charge_overdue",
        "Cobrança avulsa vencida",
        "Lembra cobranças abertas sem insistir após o recebimento.",
        "charge_overdue_enabled",
        WhatsAppMessageTemplate.TemplateType.CHARGE_OVERDUE,
        WhatsAppMessageLog.MessagePurpose.CHARGE_OVERDUE,
        "charge_overdue_days_after",
        "days",
        "Dias depois do vencimento",
        "{value} dias depois",
    ),
)


class RelationshipAutomationsView(RelationshipAccessMixin, TemplateView):
    template_name = "relationships/automations.html"

    def _next_case(self, definition, settings_object):
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()
        if definition.purpose in {
            WhatsAppMessageLog.MessagePurpose.APPOINTMENT_CONFIRMATION,
            WhatsAppMessageLog.MessagePurpose.APPOINTMENT_SOON,
        }:
            hours = getattr(settings_object, definition.timing_field)
            reminder_start = now + timedelta(hours=hours)
            reminder_end = reminder_start + timedelta(minutes=60)
            return (
                Appointment.objects.select_related("patient")
                .filter(
                    status=Appointment.Status.SCHEDULED,
                    patient__active=True,
                    patient__phone__gt="",
                    starts_at__gte=reminder_start,
                    starts_at__lt=reminder_end,
                )
                .order_by("starts_at")
                .first()
            )
        if definition.purpose == WhatsAppMessageLog.MessagePurpose.BIRTHDAY:
            if local_now.time() < settings_object.birthday_send_time:
                return None
            return (
                Patient.objects.filter(
                    active=True,
                    phone__gt="",
                    birth_date__month=today.month,
                    birth_date__day=today.day,
                )
                .order_by("full_name")
                .first()
            )
        if definition.purpose in {
            WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_DUE,
            WhatsAppMessageLog.MessagePurpose.MEMBERSHIP_OVERDUE,
        }:
            if definition.key == "membership_due":
                due_date = today + timedelta(
                    days=settings_object.membership_due_days_before
                )
            elif definition.key == "membership_due_date":
                due_date = today
            else:
                due_date = today - timedelta(
                    days=settings_object.membership_overdue_days_after
                )
            return (
                Payment.objects.select_related("membership__patient")
                .filter(
                    status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
                    due_date=due_date,
                    membership__patient__active=True,
                    membership__patient__phone__gt="",
                )
                .order_by("due_date")
                .first()
            )
        charge_due_date = today - timedelta(
            days=settings_object.charge_overdue_days_after
        )
        return (
            Charge.objects.select_related("patient")
            .filter(
                status__in=[Charge.Status.OPEN, Charge.Status.OVERDUE],
                due_date=charge_due_date,
                patient__active=True,
                patient__phone__gt="",
            )
            .order_by("due_date")
            .first()
        )

    def _build_cards(self, bound_key="", bound_form=None):
        settings_object = WhatsAppAutomationSettings.load()
        templates = {
            template.template_type: template
            for template in WhatsAppMessageTemplate.ensure_defaults()
        }
        cards = []
        for definition in AUTOMATIONS:
            template = templates[definition.template_type]
            timing_value = (
                getattr(settings_object, definition.timing_field)
                if definition.timing_field
                else None
            )
            initial = {
                "enabled": getattr(settings_object, definition.enabled_field),
                "body": template.body,
            }
            if definition.timing_kind == "time":
                initial["send_time"] = timing_value
            elif definition.timing_kind in {"hours", "days"}:
                initial["timing"] = timing_value
            form = (
                bound_form
                if bound_key == definition.key and bound_form is not None
                else RelationshipAutomationForm(
                    prefix=definition.key,
                    template_type=definition.template_type,
                    timing_kind=definition.timing_kind,
                    timing_label=definition.timing_label,
                    initial=initial,
                )
            )
            logs = WhatsAppMessageLog.objects.filter(
                message_purpose=definition.purpose
            )
            last_sent = (
                logs.filter(
                    status__in=[
                        WhatsAppMessageLog.Status.SENT,
                        WhatsAppMessageLog.Status.DRY_RUN,
                    ]
                )
                .order_by("-sent_at", "-updated_at")
                .first()
            )
            last_problem = (
                logs.filter(
                    status__in=[
                        WhatsAppMessageLog.Status.FAILED,
                        WhatsAppMessageLog.Status.EXPIRED,
                        WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN,
                    ]
                )
                .order_by("-updated_at")
                .first()
            )
            timing_display = definition.timing_copy
            if timing_value is not None and "{value}" in timing_display:
                value = (
                    timing_value.strftime("%H:%M")
                    if hasattr(timing_value, "strftime")
                    else timing_value
                )
                timing_display = timing_display.format(value=value)
            cards.append(
                {
                    "definition": definition,
                    "form": form,
                    "active": getattr(settings_object, definition.enabled_field),
                    "timing_display": timing_display,
                    "preview": render_template_preview(
                        template.body,
                        definition.template_type,
                    ),
                    "next_case": self._next_case(definition, settings_object),
                    "last_sent": last_sent,
                    "last_problem": last_problem,
                }
            )
        return cards

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Automações de relacionamento",
                "automation_cards": self._build_cards(
                    kwargs.get("bound_key", ""),
                    kwargs.get("bound_form"),
                ),
            }
        )
        return context

    def post(self, request):
        key = request.POST.get("automation_key", "")
        definition = next((item for item in AUTOMATIONS if item.key == key), None)
        if not definition:
            messages.error(request, "Automação não encontrada.")
            return redirect("relationships:automations")
        form = RelationshipAutomationForm(
            request.POST,
            prefix=definition.key,
            template_type=definition.template_type,
            timing_kind=definition.timing_kind,
            timing_label=definition.timing_label,
        )
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(bound_key=definition.key, bound_form=form)
            )

        with transaction.atomic():
            settings_object = WhatsAppAutomationSettings.load()
            setattr(
                settings_object,
                definition.enabled_field,
                form.cleaned_data["enabled"],
            )
            update_fields = [definition.enabled_field]
            if definition.timing_field:
                value = (
                    form.cleaned_data["send_time"]
                    if definition.timing_kind == "time"
                    else form.cleaned_data["timing"]
                )
                setattr(settings_object, definition.timing_field, value)
                update_fields.append(definition.timing_field)
            settings_object.save(update_fields=[*update_fields, "updated_at"])

            template = WhatsAppMessageTemplate.objects.get(
                template_type=definition.template_type
            )
            template.body = form.cleaned_data["body"]
            if form.cleaned_data["enabled"]:
                template.active = True
                template.save(update_fields=["body", "active", "updated_at"])
            else:
                template.save(update_fields=["body", "updated_at"])
            WhatsAppAutomationRule.sync_system_rules(settings_object)
        messages.success(request, f"{definition.title} atualizada.")
        return redirect("relationships:automations")
