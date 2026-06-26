from django.contrib import admin

from core.models import (
    AuditLog,
    ClinicSettings,
    GoogleCalendarIntegration,
    WhatsAppIntegration,
    WhatsAppMessageLog,
    WhatsAppMessageTemplate,
)


@admin.register(ClinicSettings)
class ClinicSettingsAdmin(admin.ModelAdmin):
    list_display = ("clinic_name", "cnpj", "membership_due_reminder_days", "updated_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "model_name", "object_repr")
    list_filter = ("action", "app_label", "model_name")
    search_fields = ("actor__username", "model_name", "object_repr")
    readonly_fields = ("actor", "action", "app_label", "model_name", "object_id", "object_repr", "changes", "created_at")


@admin.register(GoogleCalendarIntegration)
class GoogleCalendarIntegrationAdmin(admin.ModelAdmin):
    list_display = ("calendar_id", "enabled", "connected_email", "last_sync_at", "updated_at")
    readonly_fields = ("access_token", "refresh_token", "token_expires_at", "last_sync_at", "last_error")


@admin.register(WhatsAppIntegration)
class WhatsAppIntegrationAdmin(admin.ModelAdmin):
    list_display = ("provider", "enabled", "dry_run", "clinic_whatsapp_number", "phone_number_id", "last_test_at", "updated_at")
    readonly_fields = ("connected_at", "last_test_at", "last_error")


@admin.register(WhatsAppMessageTemplate)
class WhatsAppMessageTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "template_type", "active", "send_time", "updated_by", "updated_at")
    list_filter = ("template_type", "active")
    search_fields = ("title", "description", "body")


@admin.register(WhatsAppMessageLog)
class WhatsAppMessageLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "recipient_name", "recipient_number", "template", "status", "scheduled_for", "sent_at")
    list_filter = ("status", "template")
    search_fields = ("recipient_name", "recipient_number", "rendered_message")
    readonly_fields = (
        "integration",
        "template",
        "patient",
        "appointment",
        "payment",
        "charge",
        "recipient_name",
        "recipient_number",
        "rendered_message",
        "status",
        "scheduled_for",
        "sent_at",
        "provider_reference",
        "error_message",
        "response_payload",
    )
