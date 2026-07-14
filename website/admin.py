from django.contrib import admin

from website.models import (
    WebsiteFAQ,
    WebsiteGalleryItem,
    WebsiteNewsletterSubscriber,
    WebsiteService,
    WebsiteSettings,
    WebsiteTestimonial,
)


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


@admin.register(WebsiteService)
class WebsiteServiceAdmin(admin.ModelAdmin):
    list_display = ("title", "display_order", "active", "updated_at")
    list_filter = ("active",)
    search_fields = ("title", "description")


@admin.register(WebsiteGalleryItem)
class WebsiteGalleryItemAdmin(admin.ModelAdmin):
    list_display = ("title", "display_order", "active", "updated_at")
    list_filter = ("active",)
    search_fields = ("title", "alt_text")


@admin.register(WebsiteNewsletterSubscriber)
class WebsiteNewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "active", "brevo_contact_synced", "consented_at")
    list_filter = ("active", "brevo_contact_synced")
    search_fields = ("email",)
