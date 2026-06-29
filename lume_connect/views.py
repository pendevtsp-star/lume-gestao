import mimetypes
import os

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from accounts.models import UserProfile
from accounts.permissions import get_profile
from lume_connect.forms import ConnectCommentForm, ConnectPostForm
from lume_connect.models import ConnectComment, ConnectLike, ConnectNotification, ConnectPost, ConnectShareLog
from lume_connect.services.caption_generator import generate_caption


def is_connect_moderator(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = get_profile(user)
    return bool(profile and profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT})


class ActiveUserRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_active:
            raise PermissionDenied("Usuario inativo nao pode acessar o Lume Connect.")
        return super().dispatch(request, *args, **kwargs)


class ConnectFeedMixin:
    paginate_by = 12
    context_object_name = "posts"

    def base_queryset(self):
        comments = (
            ConnectComment.objects.filter(is_active=True)
            .select_related("author", "author__profile")
            .order_by("created_at")
        )
        queryset = (
            ConnectPost.objects.filter(is_active=True)
            .select_related("author", "author__profile")
            .prefetch_related(Prefetch("comments", queryset=comments, to_attr="active_comments"))
            .annotate(
                likes_total=Count("likes", distinct=True),
                comments_total=Count("comments", filter=Q(comments__is_active=True), distinct=True),
            )
            .order_by("-is_pinned", "-created_at")
        )

        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(content__icontains=query) | Q(author__username__icontains=query))

        post_type = self.request.GET.get("tipo", "todos")
        if post_type == "avisos":
            queryset = queryset.filter(is_announcement=True)
        elif post_type == "fotos":
            queryset = queryset.exclude(image="")
        return queryset

    def decorate_posts(self, context):
        posts = list(context.get("posts") or [])
        post_ids = [post.pk for post in posts]
        liked_ids = set(
            ConnectLike.objects.filter(post_id__in=post_ids, user=self.request.user).values_list("post_id", flat=True)
        )
        moderator = is_connect_moderator(self.request.user)
        for post in posts:
            post.user_has_liked = post.pk in liked_ids
            post.user_can_edit = post.author_id == self.request.user.id
            post.user_can_delete = post.user_can_edit or moderator
            post.user_can_share = post.user_can_edit and bool(post.image)
            for comment in getattr(post, "active_comments", []):
                comment.user_can_edit = comment.author_id == self.request.user.id
                comment.user_can_delete = comment.user_can_edit or moderator
        context["posts"] = posts
        context["comment_form"] = ConnectCommentForm()
        context["is_connect_moderator"] = moderator
        context["selected_type"] = self.request.GET.get("tipo", "todos")
        context["q"] = self.request.GET.get("q", "").strip()
        unread_notifications = (
            ConnectNotification.objects.filter(recipient=self.request.user, is_read=False)
            .select_related("actor", "actor__profile", "post")
            .order_by("-created_at")[:8]
        )
        context["unread_notifications"] = [
            {
                "actor_name": (
                    notification.actor.profile.display_name
                    if hasattr(notification.actor, "profile")
                    else notification.actor.get_full_name() or notification.actor.username
                ),
                "notification_type": notification.notification_type,
            }
            for notification in unread_notifications
        ]
        context["unread_notifications_total"] = ConnectNotification.objects.filter(
            recipient=self.request.user,
            is_read=False,
        ).count()
        return context


class FeedView(ActiveUserRequiredMixin, ConnectFeedMixin, ListView):
    template_name = "lume_connect/feed.html"

    def get_queryset(self):
        return self.base_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["post_form"] = ConnectPostForm(user=self.request.user)
        return self.decorate_posts(context)


class ProfilePostsView(ActiveUserRequiredMixin, ConnectFeedMixin, ListView):
    template_name = "lume_connect/profile.html"

    def get_queryset(self):
        self.profile_user = get_object_or_404(get_user_model(), pk=self.kwargs["user_id"], is_active=True)
        return self.base_queryset().filter(author=self.profile_user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = getattr(self.profile_user, "profile", None)
        context["profile_user"] = self.profile_user
        context["profile_name"] = profile.display_name if profile else self.profile_user.get_full_name() or self.profile_user.username
        context["profile_avatar_url"] = profile.avatar_url if profile else ""
        context["profile_initials"] = profile.initials if profile else (context["profile_name"][:1] or "U").upper()
        return self.decorate_posts(context)


class PostCreateView(ActiveUserRequiredMixin, CreateView):
    model = ConnectPost
    form_class = ConnectPostForm
    template_name = "lume_connect/post_form.html"
    success_url = reverse_lazy("lume_connect:feed")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, "Post publicado no Lume Connect.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Novo post", "submit_label": "Publicar"})
        return context


class PostEditView(ActiveUserRequiredMixin, UpdateView):
    model = ConnectPost
    form_class = ConnectPostForm
    template_name = "lume_connect/post_form.html"
    success_url = reverse_lazy("lume_connect:feed")

    def get_queryset(self):
        return ConnectPost.objects.filter(is_active=True)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_active:
            raise PermissionDenied("Usuario inativo nao pode acessar o Lume Connect.")
        self.object = self.get_object()
        if self.object.author_id != request.user.id:
            raise PermissionDenied("Voce so pode editar seus proprios posts.")
        return super(ActiveUserRequiredMixin, self).dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Post atualizado.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"page_title": "Editar post", "submit_label": "Salvar alteracoes"})
        return context


class PostDeleteView(ActiveUserRequiredMixin, TemplateView):
    template_name = "lume_connect/confirm_delete.html"

    def get_object(self):
        return get_object_or_404(ConnectPost.objects.filter(is_active=True), pk=self.kwargs["pk"])

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_active:
            raise PermissionDenied("Usuario inativo nao pode acessar o Lume Connect.")
        self.object = self.get_object()
        if self.object.author_id != request.user.id and not is_connect_moderator(request.user):
            raise PermissionDenied("Voce nao pode excluir este post.")
        return super(ActiveUserRequiredMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_type": "post",
                "object_label": self.object.content[:120] or "post com imagem",
                "cancel_url": reverse("lume_connect:feed"),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object.is_active = False
        self.object.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Post removido do feed.")
        return redirect("lume_connect:feed")


class SharePostAccessMixin(ActiveUserRequiredMixin):
    share_post_obj = None

    def get_share_post(self):
        return get_object_or_404(ConnectPost.objects.filter(is_active=True), pk=self.kwargs["pk"])

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_active:
            raise PermissionDenied("Usuario inativo nao pode compartilhar posts.")
        self.share_post_obj = self.get_share_post()
        if self.share_post_obj.author_id != request.user.id:
            raise PermissionDenied("Apenas o autor pode compartilhar esta imagem fora do Lume Connect.")
        if not self.share_post_obj.image:
            raise PermissionDenied("Somente posts com imagem podem ser compartilhados.")
        return super(ActiveUserRequiredMixin, self).dispatch(request, *args, **kwargs)


class SharePostView(SharePostAccessMixin, TemplateView):
    template_name = "lume_connect/share_post.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        caption_result = generate_caption(self.share_post_obj)
        context.update(
            {
                "post": self.share_post_obj,
                "suggested_caption": caption_result["caption"],
                "caption_message": caption_result["message"],
                "share_platforms": ConnectShareLog.TargetPlatform,
            }
        )
        return context


class GenerateCaptionView(SharePostAccessMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, *args, **kwargs):
        caption_result = generate_caption(self.share_post_obj)
        return JsonResponse(
            {
                "caption": caption_result["caption"],
                "source": caption_result["source"],
                "message": caption_result["message"],
            }
        )


class LogShareView(SharePostAccessMixin, View):
    allowed_platforms = {choice.value for choice in ConnectShareLog.TargetPlatform}

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, *args, **kwargs):
        platform = request.POST.get("target_platform", ConnectShareLog.TargetPlatform.OTHER)
        if platform not in self.allowed_platforms:
            platform = ConnectShareLog.TargetPlatform.OTHER
        log = ConnectShareLog.objects.create(
            post=self.share_post_obj,
            user=request.user,
            target_platform=platform,
            generated_caption=request.POST.get("generated_caption", "")[:4000],
            final_caption=request.POST.get("final_caption", "")[:4000],
        )
        return JsonResponse({"ok": True, "log_id": log.pk})


class DownloadPostImageView(SharePostAccessMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, *args, **kwargs):
        ConnectShareLog.objects.create(
            post=self.share_post_obj,
            user=request.user,
            target_platform=ConnectShareLog.TargetPlatform.DOWNLOAD,
            generated_caption=request.POST.get("generated_caption", "")[:4000],
            final_caption=request.POST.get("final_caption", "")[:4000],
        )
        filename = os.path.basename(self.share_post_obj.image.name)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        image_file = self.share_post_obj.image.open("rb")
        return FileResponse(image_file, as_attachment=True, filename=filename, content_type=content_type)


class ToggleLikeView(ActiveUserRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(ConnectPost.objects.filter(is_active=True), pk=pk)
        like = ConnectLike.objects.filter(post=post, user=request.user).first()
        if like:
            like.delete()
            liked = False
        else:
            ConnectLike.objects.create(post=post, user=request.user)
            liked = True
            if post.author_id != request.user.id:
                ConnectNotification.objects.create(
                    recipient=post.author,
                    actor=request.user,
                    post=post,
                    notification_type=ConnectNotification.NotificationType.LIKE,
                )

        likes_count = post.likes.count()
        wants_json = (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("accept", "")
        )
        if wants_json:
            return JsonResponse({"liked": liked, "likes_count": likes_count})
        return redirect(request.POST.get("next") or "lume_connect:feed")


class AddCommentView(ActiveUserRequiredMixin, View):
    def post(self, request, pk):
        post = get_object_or_404(ConnectPost.objects.filter(is_active=True), pk=pk)
        form = ConnectCommentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Nao foi possivel publicar o comentario.")
            return redirect("lume_connect:feed")
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()
        if post.author_id != request.user.id:
            ConnectNotification.objects.create(
                recipient=post.author,
                actor=request.user,
                post=post,
                comment=comment,
                notification_type=ConnectNotification.NotificationType.COMMENT,
            )
        messages.success(request, "Comentario publicado.")
        return redirect(request.POST.get("next") or "lume_connect:feed")


class CommentEditView(ActiveUserRequiredMixin, UpdateView):
    model = ConnectComment
    form_class = ConnectCommentForm
    template_name = "lume_connect/comment_form.html"

    def get_queryset(self):
        return ConnectComment.objects.filter(is_active=True, post__is_active=True)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_active:
            raise PermissionDenied("Usuario inativo nao pode acessar o Lume Connect.")
        self.object = self.get_object()
        if self.object.author_id != request.user.id:
            raise PermissionDenied("Voce so pode editar seus proprios comentarios.")
        return super(ActiveUserRequiredMixin, self).dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("lume_connect:feed")

    def form_valid(self, form):
        messages.success(self.request, "Comentario atualizado.")
        return super().form_valid(form)


class CommentDeleteView(ActiveUserRequiredMixin, TemplateView):
    template_name = "lume_connect/confirm_delete.html"

    def get_object(self):
        return get_object_or_404(ConnectComment.objects.filter(is_active=True), pk=self.kwargs["pk"])

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_active:
            raise PermissionDenied("Usuario inativo nao pode acessar o Lume Connect.")
        self.object = self.get_object()
        if self.object.author_id != request.user.id and not is_connect_moderator(request.user):
            raise PermissionDenied("Voce nao pode excluir este comentario.")
        return super(ActiveUserRequiredMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "object_type": "comentario",
                "object_label": self.object.content[:120],
                "cancel_url": reverse("lume_connect:feed"),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object.is_active = False
        self.object.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Comentario removido.")
        return redirect("lume_connect:feed")


class MarkNotificationsReadView(ActiveUserRequiredMixin, View):
    def post(self, request):
        ConnectNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return redirect("lume_connect:feed")
