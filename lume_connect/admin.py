from django.contrib import admin
from django.db.models import Count

from lume_connect.models import ConnectComment, ConnectLike, ConnectNotification, ConnectPost, ConnectShareLog


@admin.register(ConnectPost)
class ConnectPostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "author",
        "short_content",
        "is_pinned",
        "is_announcement",
        "is_active",
        "likes_total",
        "comments_total",
        "created_at",
    )
    list_filter = ("is_pinned", "is_announcement", "is_active", "created_at")
    search_fields = ("author__username", "author__first_name", "author__last_name", "content")
    readonly_fields = ("created_at", "updated_at", "likes_total", "comments_total")
    actions = ("activate_posts", "deactivate_posts")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_likes_total=Count("likes"), _comments_total=Count("comments"))

    @admin.display(description="conteudo")
    def short_content(self, obj):
        return (obj.content[:80] + "...") if len(obj.content) > 80 else obj.content

    @admin.display(description="curtidas", ordering="_likes_total")
    def likes_total(self, obj):
        return obj.likes.count() if obj.pk and not hasattr(obj, "_likes_total") else obj._likes_total

    @admin.display(description="comentarios", ordering="_comments_total")
    def comments_total(self, obj):
        return obj.comments.count() if obj.pk and not hasattr(obj, "_comments_total") else obj._comments_total

    @admin.action(description="Ativar posts selecionados")
    def activate_posts(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Desativar posts selecionados")
    def deactivate_posts(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(ConnectLike)
class ConnectLikeAdmin(admin.ModelAdmin):
    list_display = ("post", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("post__content", "user__username", "user__first_name", "user__last_name")
    readonly_fields = ("created_at",)


@admin.register(ConnectComment)
class ConnectCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "author", "short_content", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("post__content", "author__username", "author__first_name", "author__last_name", "content")
    readonly_fields = ("created_at", "updated_at")
    actions = ("activate_comments", "deactivate_comments")

    @admin.display(description="comentario")
    def short_content(self, obj):
        return (obj.content[:80] + "...") if len(obj.content) > 80 else obj.content

    @admin.action(description="Ativar comentarios selecionados")
    def activate_comments(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Desativar comentarios selecionados")
    def deactivate_comments(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(ConnectNotification)
class ConnectNotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "actor", "notification_type", "post", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("recipient__username", "actor__username", "post__content")
    readonly_fields = ("created_at",)


@admin.register(ConnectShareLog)
class ConnectShareLogAdmin(admin.ModelAdmin):
    list_display = ("post", "user", "target_platform", "created_at")
    list_filter = ("target_platform", "created_at")
    search_fields = ("post__content", "user__username", "user__first_name", "user__last_name", "final_caption")
    readonly_fields = ("created_at",)
