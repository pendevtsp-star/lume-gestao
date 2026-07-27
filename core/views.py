"""Compatibility facade for the core web views.

Concrete view implementations live in focused modules under ``core.web``.
This module keeps the historical import surface stable for application code,
tests, and third-party integrations.
"""

from core.integrations.whatsapp import (
    send_whatsapp_text,
    whatsapp_web_gateway_qr,
    whatsapp_web_gateway_restart,
    whatsapp_web_gateway_status,
)
from core.web.dashboard import (
    WEEKDAY_LABELS,
    DashboardView,
    birthday_date_for_year,
    birthday_in_period,
    weekly_birthday_patients,
)
from core.web.integrations import (
    BirthdayWhatsAppSendView,
    GoogleCalendarCallbackView,
    GoogleCalendarConnectView,
    GoogleCalendarIcsFeedView,
    GoogleCalendarSyncView,
    IntegrationsView,
    WhatsAppWebGatewayQrView,
    WhatsAppWebGatewayStatusView,
    build_whatsapp_message_context,
    default_professional_for_patient,
    escape_ics_value,
    format_ics_datetime,
    whatsapp_preview_context,
    whatsapp_target_number,
)
from core.web.mixins import FormContextMixin, SearchableListView
from core.web.settings import (
    AuditLogListView,
    BrevoTransactionalWebhookView,
    ClinicSettingsUpdateView,
    HealthCheckView,
    LegalDocumentView,
)

__all__ = [
    "AuditLogListView",
    "BirthdayWhatsAppSendView",
    "BrevoTransactionalWebhookView",
    "ClinicSettingsUpdateView",
    "DashboardView",
    "FormContextMixin",
    "GoogleCalendarCallbackView",
    "GoogleCalendarConnectView",
    "GoogleCalendarIcsFeedView",
    "GoogleCalendarSyncView",
    "HealthCheckView",
    "IntegrationsView",
    "LegalDocumentView",
    "SearchableListView",
    "WEEKDAY_LABELS",
    "WhatsAppWebGatewayQrView",
    "WhatsAppWebGatewayStatusView",
    "birthday_date_for_year",
    "birthday_in_period",
    "build_whatsapp_message_context",
    "default_professional_for_patient",
    "escape_ics_value",
    "format_ics_datetime",
    "send_whatsapp_text",
    "weekly_birthday_patients",
    "whatsapp_preview_context",
    "whatsapp_target_number",
    "whatsapp_web_gateway_qr",
    "whatsapp_web_gateway_restart",
    "whatsapp_web_gateway_status",
]
