from datetime import datetime, time, timedelta
from datetime import timezone as datetime_timezone

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from accounts.permissions import FinanceAccessMixin
from billing.models import Charge, Membership, Payment, ServicePlan
from core.forms import (
    CustomWhatsAppMessageTemplateForm,
    GoogleCalendarIntegrationForm,
    WhatsAppAppointmentSendForm,
    WhatsAppAutomationRuleForm,
    WhatsAppAutomationSettingsForm,
    WhatsAppBirthdaySendForm,
    WhatsAppChargeSendForm,
    WhatsAppIntegrationForm,
    WhatsAppMessageTemplateForm,
)
from core.integrations.google_calendar import (
    build_google_authorization_url,
    exchange_google_code,
    google_calendar_configured,
    google_oauth_credentials,
    google_redirect_uri,
    sync_upcoming_appointments,
)
from core.integrations.http import IntegrationError
from core.web.throttling import FixedWindowRateLimitMixin
from core.integrations.whatsapp import (
    format_whatsapp_currency,
    process_scheduled_whatsapp_messages,
    provider_reference_from_response,
    render_whatsapp_template,
    send_whatsapp_text as _send_whatsapp_text,
    whatsapp_connection_guidance,
    whatsapp_runtime_state,
    whatsapp_web_gateway_qr as _whatsapp_web_gateway_qr,
    whatsapp_web_gateway_restart as _whatsapp_web_gateway_restart,
    whatsapp_web_gateway_status as _whatsapp_web_gateway_status,
)
from core.models import (
    ClinicSettings,
    GoogleCalendarIntegration,
    WhatsAppAutomationRule,
    WhatsAppAutomationSettings,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from core.services.whatsapp_automation import enqueue_automatic_whatsapp_messages
from core.services.whatsapp_configuration import (
    automation_rule_operational_states,
    template_variable_documentation,
    whatsapp_web_connection_state,
)
from core.services.whatsapp_delivery_policy import can_retry_manually
from patients.models import Patient, ProfessionalPatientAssignment
from patients.services import professional_ids_for_patient
from scheduling.models import Appointment
from team.models import Professional


def _compat_dependency(name, fallback):
    """Resolve legacy patch points exposed by core.views at call time."""
    from core import views as legacy_views

    dependency = getattr(legacy_views, name, fallback)
    if dependency is globals().get(name):
        return fallback
    return dependency


def send_whatsapp_text(*args, **kwargs):
    return _compat_dependency("send_whatsapp_text", _send_whatsapp_text)(*args, **kwargs)


def whatsapp_web_gateway_qr(*args, **kwargs):
    return _compat_dependency("whatsapp_web_gateway_qr", _whatsapp_web_gateway_qr)(*args, **kwargs)


def whatsapp_web_gateway_restart(*args, **kwargs):
    return _compat_dependency("whatsapp_web_gateway_restart", _whatsapp_web_gateway_restart)(*args, **kwargs)


def whatsapp_web_gateway_status(*args, **kwargs):
    return _compat_dependency("whatsapp_web_gateway_status", _whatsapp_web_gateway_status)(*args, **kwargs)


def escape_ics_value(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def format_ics_datetime(value):
    return value.astimezone(datetime_timezone.utc).strftime("%Y%m%dT%H%M%SZ")

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
        membership = Membership(patient=sample_patient, plan=ServicePlan(name="Pilates", category=ServicePlan.Category.PILATES, monthly_price=0))
        sample_payment = Payment(membership=membership, due_date=timezone.localdate() + timedelta(days=5), amount="320.00")
        return build_whatsapp_message_context(payment=sample_payment, professional=sample_professional)
    if template_type == WhatsAppMessageTemplate.TemplateType.BIRTHDAY:
        return build_whatsapp_message_context(patient=sample_patient, professional=sample_professional)
    return build_whatsapp_message_context(appointment=sample_appointment)


def whatsapp_target_number(custom_number, patient=None):
    if custom_number:
        return custom_number
    if patient and patient.phone:
        return patient.phone
    raise IntegrationError("O destinatario selecionado nao possui telefone cadastrado. Informe um numero manualmente.")


class IntegrationsView(FixedWindowRateLimitMixin, FinanceAccessMixin, TemplateView):
    rate_limit = 60
    rate_period = 60
    rate_scope = "integrations-write"
    template_name = "core/integrations.html"

    WHATSAPP_TABS = {"panel", "connections", "messages", "diagnostics"}
    MESSAGE_TABS = {
        WhatsAppMessageTemplate.TemplateType.APPOINTMENT,
        WhatsAppMessageTemplate.TemplateType.SESSION_SOON,
        WhatsAppMessageTemplate.TemplateType.CHARGE,
        WhatsAppMessageTemplate.TemplateType.BIRTHDAY,
    }

    def get(self, request, *args, **kwargs):
        tab = request.GET.get("tab", "")
        if tab == "messages":
            return redirect("relationships:automations")
        if tab == "panel":
            return redirect("relationships:history")
        if tab == "connections":
            return redirect("whatsapp_settings")
        if tab == "diagnostics":
            if request.user.is_superuser:
                return redirect("whatsapp_support")
            return redirect("whatsapp_settings")
        return redirect("relationships:overview")

    def get_active_tab(self):
        selected = self.request.GET.get("tab") or self.request.POST.get("tab") or "connections"
        return selected if selected in self.WHATSAPP_TABS else "connections"

    def get_whatsapp_templates(self):
        WhatsAppMessageTemplate.ensure_defaults()
        return {
            template.template_type: template
            for template in WhatsAppMessageTemplate.objects.exclude(
                template_type=WhatsAppMessageTemplate.TemplateType.CUSTOM
            ).order_by("template_type")
        }

    def default_template_forms(self, templates):
        return {
            template_type: WhatsAppMessageTemplateForm(
                prefix=f"template-{template_type}",
                instance=template,
            )
            for template_type, template in templates.items()
        }

    def default_send_forms(self):
        return {
            WhatsAppMessageTemplate.TemplateType.APPOINTMENT: WhatsAppAppointmentSendForm(prefix="send-appointment"),
            WhatsAppMessageTemplate.TemplateType.SESSION_SOON: WhatsAppAppointmentSendForm(prefix="send-session-soon"),
            WhatsAppMessageTemplate.TemplateType.CHARGE: WhatsAppChargeSendForm(prefix="send-charge"),
            WhatsAppMessageTemplate.TemplateType.BIRTHDAY: WhatsAppBirthdaySendForm(prefix="send-birthday"),
        }

    def get_active_message_type(self):
        selected = self.request.GET.get("message") or self.request.POST.get("message") or WhatsAppMessageTemplate.TemplateType.APPOINTMENT
        return selected if selected in self.MESSAGE_TABS else WhatsAppMessageTemplate.TemplateType.APPOINTMENT

    def build_context(
        self,
        *,
        google_form=None,
        whatsapp_form=None,
        template_forms=None,
        send_forms=None,
        automation_form=None,
        automation_rule_form=None,
        custom_template_form=None,
        active_tab=None,
    ):
        google_integration = GoogleCalendarIntegration.load()
        whatsapp_integration = WhatsAppIntegration.load()
        if whatsapp_integration.provider != WhatsAppIntegration.Provider.WEB_GATEWAY:
            # The provisional release has one delivery path only. Preserve the
            # old Meta credentials in the database, but never route messages to
            # them while the QR gateway is the active channel.
            whatsapp_integration.provider = WhatsAppIntegration.Provider.WEB_GATEWAY
            whatsapp_integration.save(update_fields=["provider", "updated_at"])
        google_client_id, google_client_secret = google_oauth_credentials(google_integration)
        templates = self.get_whatsapp_templates()
        WhatsAppAutomationRule.ensure_defaults()
        automation_rules = list(
            WhatsAppAutomationRule.objects.select_related("template").order_by(
                "hours_before", "name"
            )
        )
        template_forms = template_forms or self.default_template_forms(templates)
        send_forms = send_forms or self.default_send_forms()
        log_queryset = WhatsAppMessageLog.objects.select_related(
            "template",
            "patient",
            "appointment",
            "payment",
            "charge",
        )
        recent_logs = log_queryset.exclude(status=WhatsAppMessageLog.Status.CANCELED)[:12]
        scheduled_logs = log_queryset.filter(status=WhatsAppMessageLog.Status.SCHEDULED).order_by("scheduled_for", "created_at")[:8]
        failed_logs = log_queryset.filter(
            status=WhatsAppMessageLog.Status.FAILED,
            created_at__gte=timezone.now() - timedelta(days=7),
        )[:8]
        last_processed_log = (
            log_queryset.filter(
                status__in=[
                    WhatsAppMessageLog.Status.SENT,
                    WhatsAppMessageLog.Status.DRY_RUN,
                    WhatsAppMessageLog.Status.FAILED,
                ]
            )
            .order_by("-updated_at")
            .first()
        )
        queue_health = {
            "state": "attention" if failed_logs else "healthy",
            "label": "Precisa de atencao" if failed_logs else "Fila sem falhas recentes",
            "detail": (
                f"{len(failed_logs)} falha(s) nos ultimos 7 dias."
                if failed_logs
                else "Nenhuma falha registrada nos ultimos 7 dias."
            ),
            "last_processed_at": last_processed_log.updated_at if last_processed_log else None,
        }
        active_appointment_rules = [
            rule
            for rule in automation_rules
            if rule.active
            and rule.trigger == WhatsAppAutomationRule.Trigger.APPOINTMENT_BEFORE
            and rule.template.active
        ]
        upcoming_automation_limit = timezone.now() + timedelta(
            hours=max([rule.hours_before for rule in active_appointment_rules] or [24]) + 1
        )
        eligible_appointments = Appointment.objects.filter(
            status=Appointment.Status.SCHEDULED,
            patient__active=True,
            patient__phone__gt="",
            starts_at__gt=timezone.now(),
            starts_at__lte=upcoming_automation_limit,
        ).count()
        recent_automatic_logs = log_queryset.exclude(automation_key="")[:10]
        last_automatic_log = log_queryset.exclude(automation_key="").order_by("-updated_at").first()
        worker_recent = bool(
            last_processed_log
            and last_processed_log.updated_at >= timezone.now() - timedelta(minutes=20)
        )
        automation_monitor = {
            "checks": [
                {
                    "label": "Canal de envio",
                    "ok": bool(whatsapp_integration.is_connected),
                    "detail": (
                        "WhatsApp conectado e liberado para a fila."
                        if whatsapp_integration.is_connected
                        else "Conecte o WhatsApp; sem canal ativo nenhuma automacao entra na fila."
                    ),
                },
                {
                    "label": "Regras da agenda",
                    "ok": bool(active_appointment_rules),
                    "detail": (
                        f"{len(active_appointment_rules)} regra(s) ativa(s)."
                        if active_appointment_rules
                        else "Ative ao menos um lembrete de agenda."
                    ),
                },
                {
                    "label": "Ultimo processamento com resultado",
                    "ok": worker_recent,
                    "detail": (
                        "A fila registrou envio, simulacao ou falha nos ultimos 20 minutos."
                        if worker_recent
                        else "Sem resultado recente; processe a fila agora se houver sessoes ou cobrancas elegiveis."
                    ),
                },
            ],
            "eligible_appointments": eligible_appointments,
            "last_automatic_at": last_automatic_log.updated_at if last_automatic_log else None,
            "recent_logs": recent_automatic_logs,
        }
        previews = {
            template_type: render_whatsapp_template(template.body, whatsapp_preview_context(template_type))
            for template_type, template in templates.items()
        }
        google_ics_url = ""
        if google_integration.has_calendar_feed:
            path = reverse("integrations_google_ics_feed", args=[google_integration.calendar_feed_token])
            google_ics_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}{path}" if settings.PUBLIC_BASE_URL else self.request.build_absolute_uri(path)
        whatsapp_guidance = whatsapp_connection_guidance(whatsapp_integration, templates.values())
        whatsapp_status = whatsapp_guidance["state"]
        whatsapp_web_gateway = whatsapp_web_gateway_status()
        whatsapp_connection_state = whatsapp_web_connection_state(
            whatsapp_web_gateway,
            enabled=whatsapp_integration.enabled,
        )
        automation_rule_states = automation_rule_operational_states(automation_rules)
        active_message_type = self.get_active_message_type()
        whatsapp_template_readiness = [
            {
                "template": template,
                "ready": bool(template.active),
                "status": "Ativo" if template.active else "Pausado",
            }
            for template in templates.values()
            if template.active
        ]
        diagnostics = [
            ("Canal WhatsApp", "WhatsApp Web"),
            ("Status WhatsApp", whatsapp_status["label"]),
            ("Modo teste WhatsApp", "Sim" if whatsapp_status["dry_run"] else "Nao"),
            ("Numero da clinica", whatsapp_integration.clinic_whatsapp_number or "Nao informado"),
            ("Gateway WhatsApp Web", "Sim" if settings.WHATSAPP_WEB_GATEWAY_URL else "Nao"),
            (
                "Sessao WhatsApp Web",
                "Conectada" if whatsapp_web_gateway.get("ready") else "Aguardando QR",
            ),
            ("Modelos ativos", str(whatsapp_status["active_templates_total"])),
            ("Google OAuth configurado", "Sim" if google_calendar_configured() else "Nao"),
            ("Google conectado", "Sim" if google_integration.is_connected else "Nao"),
            ("Link .ics ativo", "Sim" if google_integration.has_calendar_feed else "Nao"),
            (
                "Ultima atividade da fila",
                last_processed_log.updated_at.strftime("%d/%m/%Y %H:%M") if last_processed_log else "-",
            ),
        ]
        return {
            "google_form": google_form or GoogleCalendarIntegrationForm(prefix="google", instance=google_integration),
            "whatsapp_form": whatsapp_form or WhatsAppIntegrationForm(prefix="whatsapp", instance=whatsapp_integration),
            "google": google_integration,
            "whatsapp": whatsapp_integration,
            "whatsapp_status": whatsapp_status,
            "whatsapp_connection_tips": whatsapp_guidance["tips"],
            "whatsapp_friendly_error_title": whatsapp_guidance["error_title"],
            "whatsapp_friendly_error_detail": whatsapp_guidance["error_detail"],
            "whatsapp_show_debug_hint": whatsapp_guidance["show_debug_hint"],
            "whatsapp_web_gateway": whatsapp_web_gateway,
            "whatsapp_connection_state": whatsapp_connection_state,
            "whatsapp_channel_name": "WhatsApp Web",
            "google_operational": False,
            "whatsapp_template_readiness": whatsapp_template_readiness,
            "google_configured": google_calendar_configured(),
            "google_callback_url": google_redirect_uri(self.request),
            "google_ics_url": google_ics_url,
            "google_uses_env_credentials": bool(
                google_client_id
                and google_client_secret
                and not google_integration.oauth_client_id
                and not google_integration.oauth_client_secret
            ),
            "whatsapp_embedded_configured": False,
            "whatsapp_embedded_enabled": False,
            "whatsapp_embedded_app_id": "",
            "whatsapp_embedded_config_id": "",
            "whatsapp_uses_env_credentials": False,
            "whatsapp_templates": templates,
            "custom_whatsapp_templates": WhatsAppMessageTemplate.objects.filter(
                template_type=WhatsAppMessageTemplate.TemplateType.CUSTOM
            ).order_by("title"),
            "template_forms": template_forms,
            "send_forms": send_forms,
            "automation_form": automation_form
            or WhatsAppAutomationSettingsForm(prefix="automation", instance=WhatsAppAutomationSettings.load()),
            "automation_rules": automation_rules,
            "automation_rule_states": automation_rule_states,
            "automation_rule_form": automation_rule_form or WhatsAppAutomationRuleForm(prefix="rule"),
            "custom_template_form": custom_template_form or CustomWhatsAppMessageTemplateForm(prefix="custom-template"),
            "preview_messages": previews,
            "template_variable_docs": {
                template_type: template_variable_documentation(template_type)
                for template_type in templates
            },
            "active_template_variable_docs": template_variable_documentation(
                active_message_type
            ),
            "active_message_type": active_message_type,
            "recent_logs": recent_logs,
            "scheduled_logs": scheduled_logs,
            "failed_logs": failed_logs,
            "queue_health": queue_health,
            "automation_monitor": automation_monitor,
            "connected_numbers_total": 1 if whatsapp_integration.is_connected else 0,
            "sent_messages_total": log_queryset.filter(
                status__in=[
                    WhatsAppMessageLog.Status.SENT,
                    WhatsAppMessageLog.Status.DRY_RUN,
                ]
            ).count(),
            "scheduled_messages_total": log_queryset.filter(status=WhatsAppMessageLog.Status.SCHEDULED).count(),
            "active_templates_total": sum(1 for template in templates.values() if template.active),
            "diagnostics": diagnostics,
            "active_tab": active_tab or self.get_active_tab(),
            "page_title": "Integracoes",
            "section_label": "Gerencia",
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_context())
        return context

    def render_with_forms(self, **kwargs):
        return self.render_to_response(self.build_context(**kwargs))

    def create_whatsapp_log(
        self,
        *,
        integration,
        template,
        related,
        rendered_message,
        recipient_name,
        recipient_number,
        status,
        response_payload=None,
        provider_reference="",
        error_message="",
        scheduled_for=None,
        sent_at=None,
    ):
        appointment = related["appointment"]
        return WhatsAppMessageLog.objects.create(
            integration=integration,
            template=template,
            patient=related["patient"],
            appointment=related["appointment"],
            payment=related["payment"],
            charge=related["charge"],
            recipient_name=recipient_name,
            recipient_number=recipient_number,
            rendered_message=rendered_message,
            status=status,
            response_payload=response_payload or {},
            provider_reference=provider_reference,
            error_message=error_message,
            scheduled_for=scheduled_for,
            sent_at=sent_at,
            message_purpose=WhatsAppMessageLog.MessagePurpose.MANUAL,
            retry_policy=WhatsAppMessageLog.RetryPolicy.NONE,
            expires_at=appointment.starts_at if appointment else None,
            max_attempts=1,
        )

    def handle_save_template(self, request, template_type):
        templates = self.get_whatsapp_templates()
        template = templates[template_type]
        form = WhatsAppMessageTemplateForm(
            request.POST,
            prefix=f"template-{template_type}",
            instance=template,
        )
        if form.is_valid():
            template = form.save(commit=False)
            template.updated_by = request.user
            template.save()
            messages.success(request, f"{template.title} salva com sucesso.")
            return redirect(f"{reverse('integrations')}?tab=messages&message={template_type}")
        template_forms = self.default_template_forms(templates)
        template_forms[template_type] = form
        return self.render_with_forms(template_forms=template_forms, active_tab="messages")

    def send_template_message(self, request, template_type):
        templates = self.get_whatsapp_templates()
        template = templates[template_type]
        send_forms = self.default_send_forms()
        if template_type in {
            WhatsAppMessageTemplate.TemplateType.APPOINTMENT,
            WhatsAppMessageTemplate.TemplateType.SESSION_SOON,
        }:
            prefix = "send-appointment" if template_type == WhatsAppMessageTemplate.TemplateType.APPOINTMENT else "send-session-soon"
            form = WhatsAppAppointmentSendForm(request.POST, prefix=prefix)
            send_forms[template_type] = form
            if not form.is_valid():
                return self.render_with_forms(send_forms=send_forms, active_tab="messages")
            appointment = form.cleaned_data["appointment"]
            patient = appointment.patient
            message_context = build_whatsapp_message_context(appointment=appointment)
            related = {"patient": patient, "appointment": appointment, "payment": None, "charge": None}
        elif template_type == WhatsAppMessageTemplate.TemplateType.CHARGE:
            form = WhatsAppChargeSendForm(request.POST, prefix="send-charge")
            send_forms[template_type] = form
            if not form.is_valid():
                return self.render_with_forms(send_forms=send_forms, active_tab="messages")
            reference = form.selected_reference
            if isinstance(reference, Payment):
                patient = reference.membership.patient
                message_context = build_whatsapp_message_context(payment=reference)
                related = {"patient": patient, "appointment": None, "payment": reference, "charge": None}
            else:
                patient = reference.patient
                message_context = build_whatsapp_message_context(charge=reference)
                related = {"patient": patient, "appointment": None, "payment": None, "charge": reference}
        else:
            form = WhatsAppBirthdaySendForm(request.POST, prefix="send-birthday")
            send_forms[template_type] = form
            if not form.is_valid():
                return self.render_with_forms(send_forms=send_forms, active_tab="messages")
            patient = form.cleaned_data["patient"]
            message_context = build_whatsapp_message_context(patient=patient)
            related = {"patient": patient, "appointment": None, "payment": None, "charge": None}

        rendered_message = render_whatsapp_template(template.body, message_context)
        integration = WhatsAppIntegration.load()
        recipient_name = related["patient"].full_name if related["patient"] else "Destinatario manual"
        target_number = form.cleaned_data.get("custom_number", "")

        try:
            target_number = whatsapp_target_number(target_number, related["patient"])
        except IntegrationError as exc:
            self.create_whatsapp_log(
                integration=integration,
                template=template,
                related=related,
                rendered_message=rendered_message,
                recipient_name=recipient_name,
                recipient_number=target_number,
                status=WhatsAppMessageLog.Status.FAILED,
                error_message=str(exc),
            )
            messages.error(request, str(exc))
            return redirect(f"{reverse('integrations')}?tab=messages&message={template_type}")

        if form.cleaned_data.get("send_mode") == form.SEND_SCHEDULED:
            self.create_whatsapp_log(
                integration=integration,
                template=template,
                related=related,
                rendered_message=rendered_message,
                recipient_name=recipient_name,
                recipient_number=target_number,
                status=WhatsAppMessageLog.Status.SCHEDULED,
                scheduled_for=form.cleaned_data["scheduled_for"],
            )
            messages.success(request, "Mensagem agendada com sucesso.")
            return redirect(f"{reverse('integrations')}?tab=messages&message={template_type}")

        try:
            result = send_whatsapp_text(target_number, rendered_message, integration=integration)
        except IntegrationError as exc:
            self.create_whatsapp_log(
                integration=integration,
                template=template,
                related=related,
                rendered_message=rendered_message,
                recipient_name=recipient_name,
                recipient_number=target_number,
                status=WhatsAppMessageLog.Status.FAILED,
                error_message=str(exc),
            )
            messages.error(request, str(exc))
            return redirect(f"{reverse('integrations')}?tab=messages&message={template_type}")

        if result.get("dry_run"):
            status = WhatsAppMessageLog.Status.DRY_RUN
        else:
            status = WhatsAppMessageLog.Status.SENT
        self.create_whatsapp_log(
            integration=integration,
            template=template,
            related=related,
            rendered_message=rendered_message,
            recipient_name=recipient_name,
            recipient_number=target_number,
            status=status,
            sent_at=timezone.now(),
            provider_reference=provider_reference_from_response(result),
            response_payload=result if isinstance(result, dict) else {},
        )
        detail = "simulada" if status == WhatsAppMessageLog.Status.DRY_RUN else "enviada"
        messages.success(request, f"Mensagem {detail} com sucesso.")
        return redirect(f"{reverse('integrations')}?tab=messages&message={template_type}")

    def cancel_scheduled_message(self, request, log_id):
        scheduled_log = (
            WhatsAppMessageLog.objects.filter(pk=log_id, status=WhatsAppMessageLog.Status.SCHEDULED).first()
        )
        if not scheduled_log:
            messages.error(request, "Mensagem agendada nao encontrada.")
            return redirect(f"{reverse('integrations')}?tab=messages")

        scheduled_log.status = WhatsAppMessageLog.Status.CANCELED
        scheduled_log.save(update_fields=["status", "updated_at"])
        messages.success(request, "Mensagem agendada cancelada.")
        return redirect(f"{reverse('integrations')}?tab=messages")

        return redirect(f"{reverse('integrations')}?tab=messages")

    def retry_failed_message(self, request, log_id):
        failed_log = get_object_or_404(WhatsAppMessageLog, pk=log_id, status=WhatsAppMessageLog.Status.FAILED)
        decision = can_retry_manually(failed_log, now=timezone.now())
        if not decision.allowed:
            failed_log.status = decision.terminal_status
            failed_log.next_attempt_at = None
            failed_log.lease_until = None
            failed_log.terminal_reason = decision.reason_code
            failed_log.error_message = decision.user_message
            failed_log.save(
                update_fields=[
                    "status",
                    "next_attempt_at",
                    "lease_until",
                    "terminal_reason",
                    "error_message",
                    "updated_at",
                ]
            )
            messages.info(request, decision.user_message)
            return redirect(f"{reverse('integrations')}?tab=panel")
        failed_log.status = WhatsAppMessageLog.Status.SCHEDULED
        if not failed_log.scheduled_for:
            failed_log.scheduled_for = timezone.now()
        failed_log.next_attempt_at = timezone.now()
        failed_log.lease_until = None
        failed_log.attempt_count = 0
        failed_log.terminal_reason = ""
        failed_log.save(
            update_fields=[
                "status",
                "scheduled_for",
                "next_attempt_at",
                "lease_until",
                "attempt_count",
                "terminal_reason",
                "updated_at",
            ]
        )
        messages.success(request, "Mensagem recolocada na fila para uma nova tentativa.")
        return redirect(f"{reverse('integrations')}?tab=panel")

    def create_custom_template(self, request):
        form = CustomWhatsAppMessageTemplateForm(request.POST, prefix="custom-template")
        if form.is_valid():
            template = form.save(commit=False)
            template.template_type = WhatsAppMessageTemplate.TemplateType.CUSTOM
            template.updated_by = request.user
            template.save()
            messages.success(request, f"Modelo {template.title} criado. Agora vincule-o a uma automacao.")
            return redirect(f"{reverse('integrations')}?tab=messages")
        return self.render_with_forms(custom_template_form=form, active_tab="messages")

    def create_automation_rule(self, request):
        form = WhatsAppAutomationRuleForm(request.POST, prefix="rule")
        if form.is_valid():
            rule = form.save(commit=False)
            rule.is_system = False
            rule.save()
            messages.success(request, f"Automacao {rule.name} salva com sucesso.")
            return redirect(f"{reverse('integrations')}?tab=messages")
        return self.render_with_forms(automation_rule_form=form, active_tab="messages")

    def toggle_automation_rule(self, request, rule_id):
        rule = get_object_or_404(WhatsAppAutomationRule, pk=rule_id)
        rule.active = not rule.active
        rule.save(update_fields=["active", "updated_at"])
        messages.success(request, f"Automacao {'ativada' if rule.active else 'pausada'}.")
        return redirect(f"{reverse('integrations')}?tab=messages")

    def post(self, request):
        action = request.POST.get("action")
        if action == "save_google":
            form = GoogleCalendarIntegrationForm(request.POST, prefix="google", instance=GoogleCalendarIntegration.load())
            if form.is_valid():
                form.save()
                messages.success(request, "Configuracao do Google Agenda salva.")
                return redirect(f"{reverse('integrations')}?tab=connections")
            return self.render_with_forms(google_form=form, active_tab="connections")
        elif action == "disconnect_google":
            integration = GoogleCalendarIntegration.load()
            integration.enabled = False
            integration.access_token = ""
            integration.refresh_token = ""
            integration.token_expires_at = None
            integration.connected_email = ""
            integration.last_error = ""
            integration.save(
                update_fields=[
                    "enabled",
                    "access_token",
                    "refresh_token",
                    "token_expires_at",
                    "connected_email",
                    "last_error",
                    "updated_at",
                ]
            )
            messages.success(request, "Conta Google desconectada com sucesso.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "regenerate_google_ics":
            integration = GoogleCalendarIntegration.load()
            integration.regenerate_calendar_feed_token()
            messages.success(request, "Link seguro do calendario recriado. Atualize a assinatura no Google Agenda.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "revoke_google_ics":
            integration = GoogleCalendarIntegration.load()
            integration.revoke_calendar_feed_token()
            messages.success(request, "Link do calendario revogado com sucesso.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "save_whatsapp":
            form = WhatsAppIntegrationForm(request.POST, prefix="whatsapp", instance=WhatsAppIntegration.load())
            if form.is_valid():
                integration = form.save(commit=False)
                # While the clinic uses the provisional channel, all deliveries
                # must use the same QR-paired WhatsApp Web gateway.
                integration.provider = WhatsAppIntegration.Provider.WEB_GATEWAY
                if integration.enabled and integration.clinic_whatsapp_number and not integration.connected_at:
                    integration.connected_at = timezone.now()
                if not integration.enabled:
                    integration.connected_at = None
                integration.save()
                messages.success(request, "Configuracao do WhatsApp salva.")
                return redirect(f"{reverse('integrations')}?tab=connections")
            return self.render_with_forms(whatsapp_form=form, active_tab="connections")
        elif action == "select_whatsapp_web_gateway":
            integration = WhatsAppIntegration.load()
            integration.provider = WhatsAppIntegration.Provider.WEB_GATEWAY
            integration.enabled = True
            if integration.clinic_whatsapp_number and not integration.connected_at:
                integration.connected_at = timezone.now()
            integration.last_error = ""
            integration.save(update_fields=["provider", "enabled", "connected_at", "last_error", "updated_at"])
            messages.success(request, "WhatsApp Web selecionado. Escaneie o QR nesta tela para parear a sessao.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "restart_whatsapp_web_gateway":
            try:
                whatsapp_web_gateway_restart()
            except IntegrationError as exc:
                messages.error(request, f"Nao foi possivel gerar um novo QR agora: {exc}")
            else:
                messages.success(request, "Sessao do WhatsApp Web reiniciada. Aguarde alguns segundos para o QR aparecer.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "disconnect_whatsapp":
            integration = WhatsAppIntegration.load()
            integration.enabled = False
            integration.access_token = ""
            integration.connected_at = None
            integration.last_error = ""
            integration.save(update_fields=["enabled", "access_token", "connected_at", "last_error", "updated_at"])
            try:
                whatsapp_web_gateway_restart()
            except IntegrationError as exc:
                messages.warning(
                    request,
                    f"WhatsApp desligado no Lume, mas nao foi possivel limpar a sessao do gateway agora: {exc}",
                )
            else:
                messages.success(request, "WhatsApp desconectado. Aguarde alguns segundos para o novo QR aparecer.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "finish_whatsapp_embedded":
            messages.info(request, "A conexao oficial da Meta esta desativada nesta versao. Use o QR do WhatsApp Web.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "test_whatsapp":
            number = request.POST.get("test_number", "")
            message = request.POST.get("test_message", "Teste de mensagem do Lume Gestao.")
            integration = WhatsAppIntegration.load()
            status = whatsapp_runtime_state(integration)
            if not status["dry_run"] and request.POST.get("confirm_live_test") != "on":
                messages.error(
                    request,
                    "Confirme o envio real controlado antes de disparar teste fora do modo seguro.",
                )
                return redirect(f"{reverse('integrations')}?tab=connections")
            try:
                result = send_whatsapp_text(number, message, integration=integration)
            except IntegrationError as exc:
                WhatsAppIntegration.objects.filter(pk=1).update(last_error=str(exc))
                messages.error(request, str(exc))
            else:
                if result.get("dry_run"):
                    detail = "modo teste"
                elif result.get("provider") == "whatsapp_web":
                    detail = "enviado pelo WhatsApp Web"
                else:
                    detail = "enviado pela API"
                messages.success(request, f"WhatsApp validado em {detail}.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "save_automation":
            form = WhatsAppAutomationSettingsForm(
                request.POST,
                prefix="automation",
                instance=WhatsAppAutomationSettings.load(),
            )
            if form.is_valid():
                automation_settings = form.save()
                WhatsAppAutomationRule.sync_system_rules(automation_settings)
                messages.success(request, "Automacoes do WhatsApp salvas com sucesso.")
                return redirect(f"{reverse('integrations')}?tab=messages&message={self.get_active_message_type()}")
            return self.render_with_forms(automation_form=form, active_tab="messages")
        elif action == "create_custom_template":
            return self.create_custom_template(request)
        elif action == "create_automation_rule":
            return self.create_automation_rule(request)
        elif action and action.startswith("toggle_automation_rule:"):
            return self.toggle_automation_rule(request, action.split(":", 1)[1])
        elif action == "run_scheduled_whatsapp":
            enqueue_automatic_whatsapp_messages(limit=20)
            summary = process_scheduled_whatsapp_messages(limit=20)
            if summary["failed"]:
                messages.warning(
                    request,
                    f"Fila processada com alertas: {summary['processed']} item(ns), {summary['failed']} falha(s).",
                )
            else:
                messages.success(request, f"Fila processada: {summary['processed']} item(ns).")
            return redirect(f"{reverse('integrations')}?tab=panel")
        elif action and action.startswith("save_template:"):
            return self.handle_save_template(request, action.split(":", 1)[1])
        elif action and action.startswith("send_template:"):
            return self.send_template_message(request, action.split(":", 1)[1])
        elif action and action.startswith("cancel_scheduled:"):
            return self.cancel_scheduled_message(request, action.split(":", 1)[1])
        elif action and action.startswith("retry_failed:"):
            return self.retry_failed_message(request, action.split(":", 1)[1])

        messages.error(request, "Acao de integracao invalida.")
        return redirect(f"{reverse('integrations')}?tab={self.get_active_tab()}")


class BirthdayWhatsAppSendView(FixedWindowRateLimitMixin, FinanceAccessMixin, View):
    rate_limit = 20
    rate_period = 60
    rate_scope = "birthday-whatsapp-send"
    def post(self, request, patient_pk):
        WhatsAppMessageTemplate.ensure_defaults()
        patient = get_object_or_404(Patient.objects.filter(active=True, birth_date__isnull=False), pk=patient_pk)
        template = WhatsAppMessageTemplate.objects.get(template_type=WhatsAppMessageTemplate.TemplateType.BIRTHDAY)
        integration = WhatsAppIntegration.load()
        related = {"patient": patient, "appointment": None, "payment": None, "charge": None}
        rendered_message = render_whatsapp_template(template.body, build_whatsapp_message_context(patient=patient))

        if not template.active:
            messages.error(request, "O modelo de mensagem de aniversario esta pausado.")
            return redirect("dashboard")

        target_number = ""
        try:
            target_number = whatsapp_target_number("", patient)
        except IntegrationError as exc:
            WhatsAppMessageLog.objects.create(
                integration=integration,
                template=template,
                patient=related["patient"],
                appointment=related["appointment"],
                payment=related["payment"],
                charge=related["charge"],
                recipient_name=patient.full_name,
                recipient_number=target_number,
                rendered_message=rendered_message,
                status=WhatsAppMessageLog.Status.FAILED,
                error_message=str(exc),
            )
            messages.error(request, str(exc))
            return redirect("dashboard")

        try:
            result = send_whatsapp_text(target_number, rendered_message, integration=integration)
        except IntegrationError as exc:
            WhatsAppMessageLog.objects.create(
                integration=integration,
                template=template,
                patient=related["patient"],
                appointment=related["appointment"],
                payment=related["payment"],
                charge=related["charge"],
                recipient_name=patient.full_name,
                recipient_number=target_number,
                rendered_message=rendered_message,
                status=WhatsAppMessageLog.Status.FAILED,
                error_message=str(exc),
            )
            messages.error(request, str(exc))
            return redirect("dashboard")

        status = WhatsAppMessageLog.Status.DRY_RUN if result.get("dry_run") else WhatsAppMessageLog.Status.SENT
        WhatsAppMessageLog.objects.create(
            integration=integration,
            template=template,
            patient=related["patient"],
            appointment=related["appointment"],
            payment=related["payment"],
            charge=related["charge"],
            recipient_name=patient.full_name,
            recipient_number=target_number,
            rendered_message=rendered_message,
            status=status,
            sent_at=timezone.now(),
            provider_reference=provider_reference_from_response(result),
            response_payload=result if isinstance(result, dict) else {},
        )
        detail = "simulada" if status == WhatsAppMessageLog.Status.DRY_RUN else "enviada"
        messages.success(request, f"Mensagem de aniversario {detail} para {patient.full_name}.")
        return redirect("dashboard")


class WhatsAppWebGatewayStatusView(FinanceAccessMixin, View):
    def get(self, request):
        return JsonResponse(whatsapp_web_gateway_status())


class WhatsAppWebGatewayQrView(FinanceAccessMixin, View):
    def get(self, request):
        try:
            return JsonResponse(whatsapp_web_gateway_qr())
        except IntegrationError as exc:
            return JsonResponse({"ok": False, "ready": False, "error": str(exc)}, status=503)


class GoogleCalendarConnectView(FinanceAccessMixin, View):
    def get(self, request):
        try:
            return redirect(build_google_authorization_url(request))
        except IntegrationError as exc:
            messages.error(request, str(exc))
            return redirect("integrations")


class GoogleCalendarCallbackView(FinanceAccessMixin, View):
    def get(self, request):
        state = request.GET.get("state")
        expected_state = request.session.pop("google_calendar_oauth_state", "")
        if not state or state != expected_state:
            messages.error(request, "Retorno do Google Agenda invalido. Tente conectar novamente.")
            return redirect("integrations")
        code = request.GET.get("code")
        if not code:
            messages.error(request, "Google Agenda nao retornou autorizacao.")
            return redirect("integrations")
        try:
            integration = exchange_google_code(request, code)
        except IntegrationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Google Agenda conectado: {integration.connected_email or integration.calendar_id}.")
        return redirect("integrations")


class GoogleCalendarSyncView(FixedWindowRateLimitMixin, FinanceAccessMixin, View):
    rate_limit = 10
    rate_period = 60
    rate_scope = "google-calendar-sync"
    def post(self, request):
        try:
            synced, failed = sync_upcoming_appointments()
        except IntegrationError as exc:
            messages.error(request, str(exc))
        else:
            if failed:
                messages.warning(request, f"Sincronizacao parcial: {synced} enviados, {failed} com falha.")
            else:
                messages.success(request, f"Google Agenda sincronizado com {synced} agendamento(s).")
        return redirect("integrations")


class GoogleCalendarIcsFeedView(View):
    def get(self, request, token):
        integration = GoogleCalendarIntegration.objects.filter(
            calendar_feed_enabled=True,
            calendar_feed_token=token,
        ).first()
        if not integration:
            raise Http404("Calendario nao encontrado.")

        now = timezone.now()
        appointments = (
            Appointment.objects.select_related("professional")
            .filter(
                starts_at__gte=now - timedelta(days=7),
                starts_at__lte=now + timedelta(days=180),
            )
            .exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED])
            .order_by("starts_at")[:1000]
        )
        generated_at = datetime.now(datetime_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Lume Gestao//Agenda Segura//PT-BR",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Lume Gestao - Agenda",
            "REFRESH-INTERVAL;VALUE=DURATION:PT30M",
            "X-PUBLISHED-TTL:PT30M",
        ]
        for appointment in appointments:
            professional_name = appointment.professional.full_name if appointment.professional_id else "Equipe Lume"
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:lume-secure-appointment-{appointment.pk}@clinicafisiolume.com.br",
                    f"DTSTAMP:{generated_at}",
                    f"DTSTART:{format_ics_datetime(appointment.starts_at)}",
                    f"DTEND:{format_ics_datetime(appointment.ends_at)}",
                    f"SUMMARY:{escape_ics_value('Atendimento Lume - ' + professional_name)}",
                    f"DESCRIPTION:{escape_ics_value('Status: ' + appointment.get_status_display())}",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        response = HttpResponse("\r\n".join(lines), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'inline; filename="lume-agenda-segura.ics"'
        response["Cache-Control"] = "private, max-age=900"
        return response
