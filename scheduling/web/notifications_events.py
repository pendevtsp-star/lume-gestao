"""Notification center and operational calendar event views."""

from scheduling.web.common import *  # noqa: F401,F403
from django.db import transaction
from core.web.throttling import FixedWindowRateLimitMixin
from core.services.whatsapp_delivery_policy import can_retry_manually


def notifications_visible_to_user(user):
    patient_ids = patients_visible_to_user(user).values_list("pk", flat=True)
    return PatientNotification.objects.filter(patient_id__in=patient_ids)

class NotificationCenterView(AppointmentAccessMixin, SearchableListView, ListView):
    model = PatientNotification
    template_name = "scheduling/notification_center.html"
    context_object_name = "notifications"
    paginate_by = 20
    search_fields = ["patient__full_name", "message", "error_message"]

    def get_queryset(self):
        queryset = notifications_visible_to_user(self.request.user).select_related(
            "patient", "appointment"
        ).order_by("status", "due_at")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(patient__full_name__icontains=query) | Q(message__icontains=query))
        selected_status = self.request.GET.get("status", "").strip()
        if selected_status in PatientNotification.Status.values:
            queryset = queryset.filter(status=selected_status)
        selected_kind = self.request.GET.get("kind", "").strip()
        if selected_kind in PatientNotification.Kind.values:
            queryset = queryset.filter(kind=selected_kind)
        selected_channel = self.request.GET.get("channel", "").strip()
        if selected_channel in PatientNotification.Channel.values:
            queryset = queryset.filter(channel=selected_channel)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = PatientNotification.Status.choices
        context["selected_status"] = self.request.GET.get("status", "").strip()
        context["kind_choices"] = PatientNotification.Kind.choices
        context["channel_choices"] = PatientNotification.Channel.choices
        context["selected_kind"] = self.request.GET.get("kind", "").strip()
        context["selected_channel"] = self.request.GET.get("channel", "").strip()
        visible_notifications = notifications_visible_to_user(self.request.user)
        context["notification_summary"] = {
            "pending": visible_notifications.filter(status=PatientNotification.Status.PENDING).count(),
            "failed": visible_notifications.filter(status=PatientNotification.Status.FAILED).count(),
            "sent": visible_notifications.filter(status=PatientNotification.Status.SENT).count(),
        }
        return context


class GenerateNotificationsView(FixedWindowRateLimitMixin, NotificationGenerationAccessMixin, View):
    rate_limit = 20
    rate_period = 60
    rate_scope = "notification-generation"
    def post(self, request):
        created = generate_operational_notifications()
        total = sum(created.values())
        messages.success(request, f"Central atualizada com {total} novo(s) aviso(s).")
        return redirect("scheduling:notifications")


class RetryNotificationView(AgendaOperationalAccessMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        notification = get_object_or_404(
            notifications_visible_to_user(request.user).select_for_update(),
            pk=pk,
        )
        if not notification.delivery_log_id:
            messages.info(request, "Este aviso ainda nao possui tentativa de envio para reenfileirar.")
            return redirect("scheduling:notifications")
        delivery_log = get_object_or_404(
            WhatsAppMessageLog.objects.select_for_update(),
            pk=notification.delivery_log_id,
        )
        if delivery_log.status != WhatsAppMessageLog.Status.FAILED:
            messages.info(
                request,
                "Este aviso não está mais em um estado que permita nova tentativa.",
            )
            return redirect("scheduling:notifications")
        decision = can_retry_manually(delivery_log, now=timezone.now())
        if not decision.allowed:
            delivery_log.status = decision.terminal_status
            delivery_log.next_attempt_at = None
            delivery_log.lease_until = None
            delivery_log.terminal_reason = decision.reason_code
            delivery_log.error_message = decision.user_message
            delivery_log.save(
                update_fields=[
                    "status",
                    "next_attempt_at",
                    "lease_until",
                    "terminal_reason",
                    "error_message",
                    "updated_at",
                ]
            )
            notification.status = (
                PatientNotification.Status.SKIPPED
                if decision.terminal_status == WhatsAppMessageLog.Status.EXPIRED
                else PatientNotification.Status.FAILED
            )
            notification.error_message = decision.user_message
            if decision.terminal_status == WhatsAppMessageLog.Status.DELIVERY_UNCERTAIN:
                notification.metadata = {
                    **(notification.metadata or {}),
                    "delivery_uncertain": True,
                }
            notification.save(
                update_fields=["status", "error_message", "metadata", "updated_at"]
            )
            messages.info(request, decision.user_message)
            return redirect("scheduling:notifications")
        delivery_log.status = WhatsAppMessageLog.Status.SCHEDULED
        if not delivery_log.scheduled_for:
            delivery_log.scheduled_for = timezone.now()
        delivery_log.next_attempt_at = timezone.now()
        delivery_log.lease_until = None
        delivery_log.attempt_count = 0
        delivery_log.error_message = ""
        delivery_log.terminal_reason = ""
        delivery_log.save(
            update_fields=[
                "status",
                "scheduled_for",
                "next_attempt_at",
                "lease_until",
                "attempt_count",
                "error_message",
                "terminal_reason",
                "updated_at",
            ]
        )
        notification.status = PatientNotification.Status.PENDING
        notification.error_message = ""
        notification.save(update_fields=["status", "error_message", "updated_at"])
        messages.success(request, "Aviso reenfileirado para nova tentativa.")
        return redirect("scheduling:notifications")


class OperationalCalendarEventListView(AgendaOperationalAccessMixin, SearchableListView, ListView):
    model = OperationalCalendarEvent
    template_name = "scheduling/operational_calendar.html"
    context_object_name = "events"
    paginate_by = 20
    search_fields = ["title", "message"]

    def get_queryset(self):
        queryset = OperationalCalendarEvent.objects.order_by("starts_on", "starts_at_time", "title")
        selected_type = self.request.GET.get("type", "").strip()
        if selected_type in OperationalCalendarEvent.EventType.values:
            queryset = queryset.filter(event_type=selected_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event_type_choices"] = OperationalCalendarEvent.EventType.choices
        context["selected_type"] = self.request.GET.get("type", "").strip()
        return context


class OperationalCalendarEventCreateView(FormContextMixin, AgendaOperationalAccessMixin, CreateView):
    model = OperationalCalendarEvent
    form_class = OperationalCalendarEventForm
    template_name = "core/form.html"
    page_title = "Novo evento operacional"
    section_label = "Agenda"
    submit_label = "Salvar evento"
    back_url_name = "scheduling:operational_calendar"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Evento operacional criado. Gere os avisos para comunicar pacientes afetados.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("scheduling:operational_calendar")


class OperationalCalendarEventUpdateView(FormContextMixin, AgendaOperationalAccessMixin, UpdateView):
    model = OperationalCalendarEvent
    form_class = OperationalCalendarEventForm
    template_name = "core/form.html"
    page_title = "Evento operacional"
    section_label = "Agenda"
    submit_label = "Salvar evento"
    back_url_name = "scheduling:operational_calendar"

    def form_valid(self, form):
        messages.success(self.request, "Evento operacional atualizado.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("scheduling:operational_calendar")


class PatientNotificationPreferenceUpdateView(FormContextMixin, AppointmentAccessMixin, UpdateView):
    model = PatientNotificationPreference
    form_class = PatientNotificationPreferenceForm
    template_name = "core/form.html"
    page_title = "Preferencias de notificacao"
    section_label = "Agenda"
    submit_label = "Salvar preferencias"
    back_url_name = "scheduling:appointments"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(
            Patient.objects.filter(pk__in=visible_patient_ids_for_user(request.user)), pk=kwargs["patient_pk"]
        )
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        preference, _created = PatientNotificationPreference.objects.get_or_create(patient=self.patient)
        return preference

    def form_valid(self, form):
        messages.success(self.request, "Preferencias de notificacao atualizadas.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("scheduling:patient_progress", kwargs={"patient_pk": self.patient.pk})
