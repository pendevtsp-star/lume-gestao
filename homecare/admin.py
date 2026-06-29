from django.contrib import admin

from homecare.models import (
    HomecareCategory,
    HomecarePaymentEvent,
    HomecarePlan,
    HomecareSubscription,
    HomecareUploadJob,
    HomecareVideo,
    HomecareVideoComment,
    HomecareVideoLike,
    HomecareVideoProgress,
)


@admin.register(HomecareCategory)
class HomecareCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order", "active")
    list_filter = ("active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(HomecarePlan)
class HomecarePlanAdmin(admin.ModelAdmin):
    list_display = ("name", "monthly_price", "billing_cycle", "active", "public_checkout_enabled")
    list_filter = ("billing_cycle", "active", "public_checkout_enabled")
    search_fields = ("name", "description", "provider_plan_reference")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(HomecareVideo)
class HomecareVideoAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "status", "is_published", "scheduled_publish_at", "updated_at")
    list_filter = ("status", "is_published", "scheduled_publish_at", "category", "difficulty")
    search_fields = ("title", "description", "author__full_name", "provider_video_id")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(HomecareSubscription)
class HomecareSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("patient", "plan", "status", "provider", "current_period_end")
    list_filter = ("status", "source", "provider", "plan")
    search_fields = ("patient__full_name", "provider_subscription_id", "external_reference")


@admin.register(HomecarePaymentEvent)
class HomecarePaymentEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "subscription", "processed_at", "created_at")
    list_filter = ("provider", "event_type", "access_token_valid")
    search_fields = ("event_id", "provider_payment_id", "provider_subscription_id", "external_reference")
    readonly_fields = ("raw_payload",)


@admin.register(HomecareVideoProgress)
class HomecareVideoProgressAdmin(admin.ModelAdmin):
    list_display = ("patient", "video", "watched_seconds", "completed", "last_watched_at")
    list_filter = ("completed",)
    search_fields = ("patient__full_name", "video__title")


@admin.register(HomecareVideoLike)
class HomecareVideoLikeAdmin(admin.ModelAdmin):
    list_display = ("video", "user", "created_at")
    search_fields = ("video__title", "user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ("video", "user")


@admin.register(HomecareVideoComment)
class HomecareVideoCommentAdmin(admin.ModelAdmin):
    list_display = ("video", "author", "parent", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("video__title", "author__username", "author__first_name", "author__last_name", "content")
    autocomplete_fields = ("video", "author", "parent")
    actions = ("activate_comments", "deactivate_comments")

    @admin.action(description="Ativar comentarios selecionados")
    def activate_comments(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Desativar comentarios selecionados")
    def deactivate_comments(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(HomecareUploadJob)
class HomecareUploadJobAdmin(admin.ModelAdmin):
    list_display = ("video", "status", "attempts", "started_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("video__title", "error_message")
