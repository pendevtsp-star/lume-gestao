from django.contrib import admin

from accounts.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "patient", "professional", "whatsapp_number", "updated_at")
    list_filter = ("role", "whatsapp_notifications_enabled")
    search_fields = ("user__username", "user__email", "patient__full_name", "professional__full_name")
