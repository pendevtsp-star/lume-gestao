from django.contrib import admin

from scheduling.models import Appointment, ProfessionalAvailability, ServicePackage, ServiceUsage


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
