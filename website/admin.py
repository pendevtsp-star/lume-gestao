from django.contrib import admin

from website.models import WebsiteFAQ, WebsiteSettings, WebsiteTestimonial


@admin.register(WebsiteSettings)
class WebsiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("clinic_name", "assistant_enabled", "whatsapp_clicks", "system_clicks", "updated_at")


@admin.register(WebsiteFAQ)
class WebsiteFAQAdmin(admin.ModelAdmin):
    list_display = ("question", "display_order", "active", "updated_at")
    list_filter = ("active",)
    search_fields = ("question", "answer")


@admin.register(WebsiteTestimonial)
class WebsiteTestimonialAdmin(admin.ModelAdmin):
    list_display = ("author_name", "author_role", "display_order", "active", "updated_at")
    list_filter = ("active",)
    search_fields = ("author_name", "author_role", "body")

