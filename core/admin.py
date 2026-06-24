from django.contrib import admin

from core.models import AuditLog, ClinicSettings


@admin.register(ClinicSettings)
class ClinicSettingsAdmin(admin.ModelAdmin):
    list_display = ("membership_due_reminder_days", "updated_at")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "model_name", "object_repr")
    list_filter = ("action", "app_label", "model_name")
    search_fields = ("actor__username", "model_name", "object_repr")
    readonly_fields = ("actor", "action", "app_label", "model_name", "object_id", "object_repr", "changes", "created_at")
