from django.contrib import admin

from scheduling.models import (
    Appointment,
    OperationalCalendarEvent,
    PatientNotification,
    PatientNotificationPreference,
    ProfessionalAvailability,
    ServicePackage,
    ServicePackageAdjustment,
    ServiceUsage,
)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "professional", "starts_at", "ends_at", "status", "service_units")
    list_filter = ("status", "professional", "starts_at")
    search_fields = ("patient__full_name", "professional__full_name")


@admin.register(ProfessionalAvailability)
class ProfessionalAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("professional", "weekday", "starts_at", "ends_at", "valid_from", "valid_until", "active")
    list_filter = ("weekday", "active", "professional")
    search_fields = ("professional__full_name", "notes")


@admin.register(ServicePackage)
class ServicePackageAdmin(admin.ModelAdmin):
    list_display = ("membership", "total_sessions", "used_sessions", "remaining_sessions", "status")
    list_filter = ("status",)
    search_fields = ("membership__patient__full_name", "membership__plan__name")


@admin.register(ServiceUsage)
class ServiceUsageAdmin(admin.ModelAdmin):
    list_display = ("service_package", "appointment", "units", "registered_by", "registered_at")
    search_fields = ("service_package__membership__patient__full_name", "appointment__patient__full_name")


@admin.register(ServicePackageAdjustment)
class ServicePackageAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("service_package", "appointment", "delta_sessions", "reason", "created_by", "created_at")
    list_filter = ("reason", "created_at")
    search_fields = ("service_package__membership__patient__full_name", "service_package__membership__plan__name", "notes")


@admin.register(OperationalCalendarEvent)
class OperationalCalendarEventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "starts_on", "ends_on", "affects_schedule", "send_notice", "active")
    list_filter = ("event_type", "active", "affects_schedule", "send_notice")
    search_fields = ("title", "message")


@admin.register(PatientNotification)
class PatientNotificationAdmin(admin.ModelAdmin):
    list_display = ("patient", "kind", "channel", "status", "due_at", "attempts")
    list_filter = ("kind", "channel", "status")
    search_fields = ("patient__full_name", "message", "error_message")


@admin.register(PatientNotificationPreference)
class PatientNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("patient", "whatsapp_enabled", "pwa_enabled", "appointment_enabled", "financial_enabled", "operational_enabled")
    list_filter = ("whatsapp_enabled", "pwa_enabled", "appointment_enabled", "financial_enabled", "operational_enabled")
    search_fields = ("patient__full_name",)
