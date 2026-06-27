from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Q, Sum
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import FinanceAccessMixin, ManagementAccessMixin, has_role, get_profile
from billing.models import Charge, Membership, Payment, ServicePlan
from core.forms import (
    ClinicSettingsForm,
    GoogleCalendarIntegrationForm,
    WhatsAppAppointmentSendForm,
    WhatsAppBirthdaySendForm,
    WhatsAppChargeSendForm,
    WhatsAppIntegrationForm,
    WhatsAppMessageTemplateForm,
)
from core.integrations.google_calendar import (
    build_google_authorization_url,
    exchange_google_code,
    google_calendar_configured,
    sync_upcoming_appointments,
)
from core.integrations.http import IntegrationError
from core.integrations.whatsapp import (
    format_whatsapp_currency,
    process_scheduled_whatsapp_messages,
    provider_reference_from_response,
    render_whatsapp_template,
    send_whatsapp_text,
)
from core.models import (
    AuditLog,
    ClinicSettings,
    GoogleCalendarIntegration,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)
from patients.models import Patient, ProfessionalPatientAssignment
from patients.services import patient_ids_for_professional, professional_ids_for_patient
from scheduling.models import Appointment, ServicePackage, ServiceUsage
from team.models import Employee, Professional


WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


class SearchableListView(LoginRequiredMixin):
    search_fields = []

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if not query:
            return queryset

        filters = Q()
        for field in self.search_fields:
            filters |= Q(**{f"{field}__icontains": query})
        return queryset.filter(filters)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["q"] = self.request.GET.get("q", "").strip()
        context["querystring"] = query_params.urlencode()
        return context


class HealthCheckView(View):
    def get(self, request):
        payload = {"status": "ok"}
        if settings.LUME_DESKTOP or (
            request.user.is_authenticated
            and (request.user.is_superuser or has_role(request.user, {UserProfile.Role.MANAGEMENT}))
        ):
            payload.update(
                {
                    "desktop_mode": settings.LUME_DESKTOP,
                    "database_engine": settings.DATABASES["default"]["ENGINE"],
                    "environment": settings.ENVIRONMENT,
                }
            )
        return JsonResponse(payload)


class FormContextMixin:
    page_title = ""
    section_label = ""
    back_url_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["section_label"] = self.section_label
        context["back_url"] = reverse(self.back_url_name)
        return context


def birthday_date_for_year(birth_date, year):
    try:
        return birth_date.replace(year=year)
    except ValueError:
        return birth_date.replace(year=year, day=28)


def birthday_in_period(birth_date, starts_on, ends_on):
    for year in range(starts_on.year, ends_on.year + 1):
        candidate = birthday_date_for_year(birth_date, year)
        if starts_on <= candidate <= ends_on:
            return candidate
    return None


def weekly_birthday_patients(queryset, starts_on=None, days=7):
    starts_on = starts_on or timezone.localdate()
    ends_on = starts_on + timedelta(days=days - 1)
    birthdays = []
    for patient in queryset.filter(birth_date__isnull=False).only("id", "full_name", "birth_date", "phone"):
        birthday_date = birthday_in_period(patient.birth_date, starts_on, ends_on)
        if not birthday_date:
            continue
        birthdays.append(
            {
                "patient": patient,
                "date": birthday_date,
                "display_date": birthday_date.strftime("%d/%m"),
                "weekday": "Hoje" if birthday_date == starts_on else WEEKDAY_LABELS[birthday_date.weekday()],
                "has_phone": bool(patient.phone),
            }
        )
    return sorted(birthdays, key=lambda birthday: (birthday["date"], birthday["patient"].full_name))


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month_start = today.replace(day=1)
        settings = ClinicSettings.load()
        reminder_limit = today + timedelta(days=settings.membership_due_reminder_days)
        profile = get_profile(self.request.user)
        finance_visible = self.request.user.is_superuser or (
            profile and profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}
        )

        patient_queryset = Patient.objects.filter(active=True)
        if profile and profile.is_patient and profile.patient_id:
            patient_queryset = patient_queryset.filter(pk=profile.patient_id)
        elif profile and profile.is_professional and profile.professional_id:
            patient_queryset = patient_queryset.filter(pk__in=patient_ids_for_professional(profile.professional))

        pending_payments = Payment.objects.filter(status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE])
        paid_this_month = Payment.objects.filter(status=Payment.Status.PAID, paid_at__gte=month_start)
        upcoming_payments = Payment.objects.filter(
            status=Payment.Status.PENDING,
            due_date__gte=today,
            due_date__lte=reminder_limit,
        )
        overdue_payments = Payment.objects.filter(status__in=[Payment.Status.OVERDUE, Payment.Status.PENDING], due_date__lt=today)
        if not finance_visible:
            pending_payments = pending_payments.none()
            paid_this_month = paid_this_month.none()
            upcoming_payments = upcoming_payments.none()
            overdue_payments = overdue_payments.none()

        appointment_queryset = (
            Appointment.objects.select_related("patient", "professional")
            .filter(starts_at__date__gte=today)
            .exclude(status__in=[Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED])
        )
        if not self.request.user.is_superuser:
            if profile and profile.is_patient and profile.patient_id:
                appointment_queryset = appointment_queryset.filter(patient=profile.patient)
            elif profile and profile.is_professional and profile.professional_id:
                appointment_queryset = appointment_queryset.filter(professional=profile.professional)

        context.update(
            {
                "finance_visible": finance_visible,
                "birthday_patients": weekly_birthday_patients(Patient.objects.filter(active=True), today),
                "birthday_week_start": today,
                "birthday_week_end": today + timedelta(days=6),
                "birthday_whatsapp_visible": finance_visible,
                "active_patients": patient_queryset.count(),
                "active_memberships": Membership.objects.filter(status=Membership.Status.ACTIVE).count() if finance_visible else 0,
                "active_professionals": Professional.objects.filter(active=True).count() if finance_visible else 0,
                "employees": Employee.objects.filter(active=True).count() if finance_visible else 0,
                "active_plans": ServicePlan.objects.filter(active=True).count() if finance_visible else 0,
                "pending_total": pending_payments.aggregate(total=Sum("amount"))["total"] or 0,
                "paid_month_total": paid_this_month.aggregate(total=Sum("amount"))["total"] or 0,
                "next_payments": pending_payments.select_related("membership__patient", "membership__plan")[:8],
                "upcoming_payments": upcoming_payments.select_related("membership__patient", "membership__plan")[:8],
                "overdue_payments": overdue_payments.select_related("membership__patient", "membership__plan")[:8],
                "next_appointments": appointment_queryset[:8],
                "reminder_days": settings.membership_due_reminder_days,
            }
        )
        if profile and profile.is_patient and profile.patient_id:
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            current_memberships = (
                Membership.objects.select_related("plan")
                .filter(patient=profile.patient, status=Membership.Status.ACTIVE)
                .order_by("plan__name")
            )
            active_packages = (
                ServicePackage.objects.select_related("membership__plan")
                .filter(membership__patient=profile.patient, status=ServicePackage.Status.ACTIVE)
                .order_by("expires_on", "created_at")
            )
            service_usages = (
                ServiceUsage.objects.select_related("appointment__professional")
                .filter(appointment__patient=profile.patient)
                .order_by("-registered_at")
            )
            weekly_allowed = sum(membership.plan.sessions_per_week for membership in current_memberships)
            weekly_used = (
                service_usages.filter(registered_at__date__gte=week_start, registered_at__date__lte=week_end)
                .aggregate(total=Sum("units"))["total"]
                or 0
            )
            package_total = sum(package.total_sessions for package in active_packages)
            package_used = sum(package.used_sessions for package in active_packages)
            next_payment = (
                Payment.objects.select_related("membership__plan")
                .filter(
                    membership__patient=profile.patient,
                    status__in=[Payment.Status.PENDING, Payment.Status.OVERDUE],
                )
                .order_by("due_date")
                .first()
            )
            context.update(
                {
                    "patient_dashboard": True,
                    "patient_memberships": current_memberships,
                    "patient_next_payment": next_payment,
                    "patient_weekly_allowed": weekly_allowed,
                    "patient_weekly_used": weekly_used,
                    "patient_weekly_remaining": max(weekly_allowed - weekly_used, 0),
                    "patient_package_total": package_total,
                    "patient_package_used": package_used,
                    "patient_package_remaining": max(package_total - package_used, 0),
                    "patient_recent_usages": service_usages[:8],
                }
            )
        return context


class AuditLogListView(ManagementAccessMixin, SearchableListView, ListView):
    model = AuditLog
    template_name = "core/audit_list.html"
    context_object_name = "logs"
    paginate_by = 20
    search_fields = ["actor__username", "model_name", "object_repr", "action"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("actor")
        action = self.request.GET.get("action", "").strip()
        model_name = self.request.GET.get("model", "").strip()
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        if action:
            queryset = queryset.filter(action=action)
        if model_name:
            queryset = queryset.filter(model_name=model_name)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = AuditLog.objects.all()
        filtered = self.get_queryset()
        context.update(
            {
                "action_choices": AuditLog.Action.choices,
                "model_choices": base_queryset.order_by("model_name")
                .values_list("model_name", flat=True)
                .distinct(),
                "selected_action": self.request.GET.get("action", ""),
                "selected_model": self.request.GET.get("model", ""),
                "date_from": self.request.GET.get("date_from", ""),
                "date_to": self.request.GET.get("date_to", ""),
                "audit_total": filtered.count(),
                "audit_created_total": filtered.filter(action=AuditLog.Action.CREATED).count(),
                "audit_updated_total": filtered.filter(action=AuditLog.Action.UPDATED).count(),
                "audit_deleted_total": filtered.filter(action=AuditLog.Action.DELETED).count(),
            }
        )
        return context


class ClinicSettingsUpdateView(ManagementAccessMixin, UpdateView):
    model = ClinicSettings
    form_class = ClinicSettingsForm
    template_name = "core/form.html"
    success_url = reverse_lazy("settings")

    def get_object(self, queryset=None):
        return ClinicSettings.load()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Configuracoes",
                "section_label": "Gerencia",
                "back_url": reverse("dashboard"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Configuracoes da clinica atualizadas com sucesso.")
        return super().form_valid(form)


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
        patient = payment.membership.patient
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


class IntegrationsView(FinanceAccessMixin, TemplateView):
    template_name = "core/integrations.html"

    WHATSAPP_TABS = {"panel", "connections", "messages"}

    def get_active_tab(self):
        selected = self.request.GET.get("tab") or self.request.POST.get("tab") or "panel"
        return selected if selected in self.WHATSAPP_TABS else "panel"

    def get_whatsapp_templates(self):
        WhatsAppMessageTemplate.ensure_defaults()
        return {
            template.template_type: template
            for template in WhatsAppMessageTemplate.objects.order_by("template_type")
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
            WhatsAppMessageTemplate.TemplateType.CHARGE: WhatsAppChargeSendForm(prefix="send-charge"),
            WhatsAppMessageTemplate.TemplateType.BIRTHDAY: WhatsAppBirthdaySendForm(prefix="send-birthday"),
        }

    def build_context(
        self,
        *,
        google_form=None,
        whatsapp_form=None,
        template_forms=None,
        send_forms=None,
        active_tab=None,
    ):
        google_integration = GoogleCalendarIntegration.load()
        whatsapp_integration = WhatsAppIntegration.load()
        templates = self.get_whatsapp_templates()
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
        previews = {
            template_type: render_whatsapp_template(template.body, whatsapp_preview_context(template_type))
            for template_type, template in templates.items()
        }
        return {
            "google_form": google_form or GoogleCalendarIntegrationForm(prefix="google", instance=google_integration),
            "whatsapp_form": whatsapp_form or WhatsAppIntegrationForm(prefix="whatsapp", instance=whatsapp_integration),
            "google": google_integration,
            "whatsapp": whatsapp_integration,
            "google_configured": google_calendar_configured(),
            "whatsapp_templates": templates,
            "template_forms": template_forms,
            "send_forms": send_forms,
            "preview_messages": previews,
            "recent_logs": recent_logs,
            "scheduled_logs": scheduled_logs,
            "connected_numbers_total": 1 if whatsapp_integration.is_connected else 0,
            "sent_messages_total": log_queryset.filter(
                status__in=[WhatsAppMessageLog.Status.SENT, WhatsAppMessageLog.Status.DRY_RUN]
            ).count(),
            "scheduled_messages_total": log_queryset.filter(status=WhatsAppMessageLog.Status.SCHEDULED).count(),
            "active_templates_total": sum(1 for template in templates.values() if template.active),
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
            return redirect(f"{reverse('integrations')}?tab=messages")
        template_forms = self.default_template_forms(templates)
        template_forms[template_type] = form
        return self.render_with_forms(template_forms=template_forms, active_tab="messages")

    def send_template_message(self, request, template_type):
        templates = self.get_whatsapp_templates()
        template = templates[template_type]
        send_forms = self.default_send_forms()
        if template_type == WhatsAppMessageTemplate.TemplateType.APPOINTMENT:
            form = WhatsAppAppointmentSendForm(request.POST, prefix="send-appointment")
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
            return redirect(f"{reverse('integrations')}?tab=messages")

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
            return redirect(f"{reverse('integrations')}?tab=messages")

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
            return redirect(f"{reverse('integrations')}?tab=messages")

        status = WhatsAppMessageLog.Status.DRY_RUN if result.get("dry_run") else WhatsAppMessageLog.Status.SENT
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
        return redirect(f"{reverse('integrations')}?tab=messages")

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

    def post(self, request):
        action = request.POST.get("action")
        if action == "save_google":
            form = GoogleCalendarIntegrationForm(request.POST, prefix="google", instance=GoogleCalendarIntegration.load())
            if form.is_valid():
                form.save()
                messages.success(request, "Configuracao do Google Agenda salva.")
                return redirect(f"{reverse('integrations')}?tab=connections")
            return self.render_with_forms(google_form=form, active_tab="connections")
        elif action == "save_whatsapp":
            form = WhatsAppIntegrationForm(request.POST, prefix="whatsapp", instance=WhatsAppIntegration.load())
            if form.is_valid():
                integration = form.save(commit=False)
                if integration.enabled and integration.clinic_whatsapp_number and not integration.connected_at:
                    integration.connected_at = timezone.now()
                if not integration.enabled:
                    integration.connected_at = None
                integration.save()
                messages.success(request, "Configuracao do WhatsApp salva.")
                return redirect(f"{reverse('integrations')}?tab=connections")
            return self.render_with_forms(whatsapp_form=form, active_tab="connections")
        elif action == "test_whatsapp":
            number = request.POST.get("test_number", "")
            message = request.POST.get("test_message", "Teste de mensagem do Lume Gestao.")
            try:
                result = send_whatsapp_text(number, message)
            except IntegrationError as exc:
                WhatsAppIntegration.objects.filter(pk=1).update(last_error=str(exc))
                messages.error(request, str(exc))
            else:
                detail = "modo teste" if result.get("dry_run") else "enviado pela API"
                messages.success(request, f"WhatsApp validado em {detail}.")
            return redirect(f"{reverse('integrations')}?tab=connections")
        elif action == "run_scheduled_whatsapp":
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

        messages.error(request, "Acao de integracao invalida.")
        return redirect(f"{reverse('integrations')}?tab={self.get_active_tab()}")


class BirthdayWhatsAppSendView(FinanceAccessMixin, View):
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


class GoogleCalendarSyncView(FinanceAccessMixin, View):
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

# Create your views here.
