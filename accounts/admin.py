from django.contrib import admin

from accounts.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "patient",
        "professional",
        "must_change_password",
        "lgpd_consent_version",
        "onboarding_delivery_method",
        "updated_at",
    )
    list_filter = ("role", "whatsapp_notifications_enabled", "must_change_password", "onboarding_delivery_method")
    search_fields = ("user__username", "user__email", "patient__full_name", "professional__full_name")
