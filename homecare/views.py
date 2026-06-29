from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import Http404
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from accounts.models import UserProfile
from accounts.permissions import get_profile
from core.integrations.http import IntegrationError
from core.views import FormContextMixin, SearchableListView
from homecare.features import homecare_checkout_enabled, homecare_public_enabled, homecare_webhook_enabled
from homecare.forms import (
    HomecareCategoryForm,
    HomecarePlanForm,
    HomecareSubscriptionForm,
    HomecareVideoCommentForm,
    HomecareVideoForm,
)
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
from homecare.permissions import HomecareAdminAccessMixin, HomecareContentAccessMixin
from homecare.services.bunny import build_bunny_embed_url
from homecare.services.payments import get_payment_provider, record_asaas_webhook, start_checkout_subscription


def included_homecare_access_for_user(user):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    profile = get_profile(user)
    if not profile:
        return False
    if profile.is_patient:
        return bool(profile.patient_id and profile.patient.active)
    return profile.role in {
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
        UserProfile.Role.VIEWER,
    }


def active_subscription_for_user(user):
    profile = get_profile(user)
    if not profile or not profile.is_patient or not profile.patient_id:
        return None
    if not profile.patient.active:
        return None
    now = timezone.now()
    return (
        HomecareSubscription.objects.select_related("plan", "patient")
        .filter(
            patient=profile.patient,
            status__in=[HomecareSubscription.Status.ACTIVE, HomecareSubscription.Status.TRIALING],
        )
        .filter(current_period_end__isnull=True)
        .first()
        or HomecareSubscription.objects.select_related("plan", "patient")
        .filter(
            patient=profile.patient,
            status__in=[HomecareSubscription.Status.ACTIVE, HomecareSubscription.Status.TRIALING],
            current_period_end__gte=now,
        )
        .order_by("-current_period_end")
        .first()
    )


def public_video_q(prefix=""):
    now = timezone.now()
    return (
        Q(**{f"{prefix}is_published": True, f"{prefix}status": HomecareVideo.Status.READY})
        & (
            Q(**{f"{prefix}scheduled_publish_at__isnull": True})
            | Q(**{f"{prefix}scheduled_publish_at__lte": now})
        )
    )


class HomecareDashboardView(HomecareContentAccessMixin, TemplateView):
    template_name = "homecare/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = get_profile(self.request.user)
        videos = HomecareVideo.objects.all()
        if profile and profile.is_professional and profile.professional_id and not self.request.user.is_superuser:
            videos = videos.filter(author=profile.professional)
        now = timezone.now()
        context.update(
            {
                "page_title": "Fisioterapia em Casa",
                "video_count": videos.count(),
                "published_count": videos.filter(public_video_q()).count(),
                "scheduled_count": videos.filter(is_published=True, scheduled_publish_at__gt=now).count(),
                "queued_count": HomecareUploadJob.objects.filter(status=HomecareUploadJob.Status.QUEUED).count(),
                "active_subscriptions": HomecareSubscription.objects.filter(status=HomecareSubscription.Status.ACTIVE).count(),
                "recent_videos": videos.select_related("category", "author")[:6],
                "recent_subscriptions": HomecareSubscription.objects.select_related("patient", "plan")[:6],
            }
        )
        return context


class HomecareCategoryListView(HomecareAdminAccessMixin, SearchableListView, ListView):
    model = HomecareCategory
    template_name = "homecare/category_list.html"
    context_object_name = "categories"
    paginate_by = 12
    search_fields = ["name", "description"]


class HomecareCategoryCreateView(FormContextMixin, HomecareAdminAccessMixin, CreateView):
    model = HomecareCategory
    form_class = HomecareCategoryForm
    template_name = "core/form.html"
    success_url = reverse_lazy("homecare:categories")
    page_title = "Categoria"
    section_label = "Conteudos"
    back_url_name = "homecare:categories"

    def form_valid(self, form):
        messages.success(self.request, "Categoria criada com sucesso.")
        return super().form_valid(form)


class HomecareCategoryUpdateView(FormContextMixin, HomecareAdminAccessMixin, UpdateView):
    model = HomecareCategory
    form_class = HomecareCategoryForm
    template_name = "core/form.html"
    success_url = reverse_lazy("homecare:categories")
    page_title = "Categoria"
    section_label = "Conteudos"
    back_url_name = "homecare:categories"

    def form_valid(self, form):
        messages.success(self.request, "Categoria atualizada com sucesso.")
        return super().form_valid(form)


class HomecarePlanListView(HomecareAdminAccessMixin, SearchableListView, ListView):
    model = HomecarePlan
    template_name = "homecare/plan_list.html"
    context_object_name = "plans"
    paginate_by = 12
    search_fields = ["name", "description"]


class HomecarePlanCreateView(FormContextMixin, HomecareAdminAccessMixin, CreateView):
    model = HomecarePlan
    form_class = HomecarePlanForm
    template_name = "core/form.html"
    success_url = reverse_lazy("homecare:plans")
    page_title = "Plano do canal"
    section_label = "Conteudos"
    back_url_name = "homecare:plans"

    def form_valid(self, form):
        messages.success(self.request, "Plano do canal criado com sucesso.")
        return super().form_valid(form)


class HomecarePlanUpdateView(FormContextMixin, HomecareAdminAccessMixin, UpdateView):
    model = HomecarePlan
    form_class = HomecarePlanForm
    template_name = "core/form.html"
    success_url = reverse_lazy("homecare:plans")
    page_title = "Plano do canal"
    section_label = "Conteudos"
    back_url_name = "homecare:plans"

    def form_valid(self, form):
        messages.success(self.request, "Plano do canal atualizado com sucesso.")
        return super().form_valid(form)


class HomecareVideoListView(HomecareContentAccessMixin, SearchableListView, ListView):
    model = HomecareVideo
    template_name = "homecare/video_list.html"
    context_object_name = "videos"
    paginate_by = 12
    search_fields = ["title", "description", "author__full_name", "category__name"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("category", "author")
        profile = get_profile(self.request.user)
        if profile and profile.is_professional and profile.professional_id and not self.request.user.is_superuser:
            queryset = queryset.filter(author=profile.professional)
        status = self.request.GET.get("status", "").strip()
        if status:
            queryset = queryset.filter(status=status)
        publication = self.request.GET.get("publication", "").strip()
        now = timezone.now()
        if publication == "published":
            queryset = queryset.filter(public_video_q())
        elif publication == "scheduled":
            queryset = queryset.filter(is_published=True, scheduled_publish_at__gt=now)
        elif publication == "draft":
            queryset = queryset.filter(is_published=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = HomecareVideo.Status.choices
        context["selected_status"] = self.request.GET.get("status", "")
        context["publication_choices"] = [
            ("published", "Disponiveis"),
            ("scheduled", "Programados"),
            ("draft", "Rascunhos"),
        ]
        context["selected_publication"] = self.request.GET.get("publication", "")
        return context


class HomecareVideoCreateView(FormContextMixin, HomecareContentAccessMixin, CreateView):
    model = HomecareVideo
    form_class = HomecareVideoForm
    template_name = "homecare/video_form.html"
    success_url = reverse_lazy("homecare:videos")
    page_title = "Video"
    section_label = "Conteudos"
    back_url_name = "homecare:videos"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        if form.cleaned_data.get("upload_file"):
            messages.success(self.request, "Video salvo e enviado para a fila de upload.")
        else:
            messages.success(self.request, "Video salvo como rascunho.")
        return response


class HomecareVideoUpdateView(FormContextMixin, HomecareContentAccessMixin, UpdateView):
    model = HomecareVideo
    form_class = HomecareVideoForm
    template_name = "homecare/video_form.html"
    success_url = reverse_lazy("homecare:videos")
    page_title = "Video"
    section_label = "Conteudos"
    back_url_name = "homecare:videos"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("author")
        profile = get_profile(self.request.user)
        if profile and profile.is_professional and profile.professional_id and not self.request.user.is_superuser:
            queryset = queryset.filter(author=profile.professional)
        return queryset

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Video atualizado com sucesso.")
        return super().form_valid(form)


class HomecareVideoRetryUploadView(HomecareContentAccessMixin, View):
    def post(self, request, pk):
        video = get_object_or_404(HomecareVideo, pk=pk)
        profile = get_profile(request.user)
        if profile and profile.is_professional and profile.professional_id and video.author_id != profile.professional_id:
            return HttpResponseForbidden("Video de outro profissional.")
        if not video.temporary_file:
            messages.error(request, "Este video nao possui arquivo temporario para reenviar.")
            return redirect("homecare:videos")
        video.status = HomecareVideo.Status.QUEUED
        video.upload_error = ""
        video.save(update_fields=["status", "upload_error", "updated_at"])
        HomecareUploadJob.objects.create(video=video)
        messages.success(request, "Upload reenviado para a fila.")
        return redirect("homecare:videos")


class HomecareSubscriptionListView(HomecareAdminAccessMixin, SearchableListView, ListView):
    model = HomecareSubscription
    template_name = "homecare/subscription_list.html"
    context_object_name = "subscriptions"
    paginate_by = 12
    search_fields = ["patient__full_name", "plan__name", "provider_subscription_id", "external_reference"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("patient", "plan")
        status = self.request.GET.get("status", "").strip()
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = HomecareSubscription.Status.choices
        context["selected_status"] = self.request.GET.get("status", "")
        return context


class HomecareSubscriptionCreateView(FormContextMixin, HomecareAdminAccessMixin, CreateView):
    model = HomecareSubscription
    form_class = HomecareSubscriptionForm
    template_name = "core/form.html"
    success_url = reverse_lazy("homecare:subscriptions")
    page_title = "Assinatura do canal"
    section_label = "Conteudos"
    back_url_name = "homecare:subscriptions"

    def form_valid(self, form):
        subscription = form.save(commit=False)
        if subscription.source == HomecareSubscription.Source.MANUAL and subscription.status == HomecareSubscription.Status.ACTIVE:
            if not subscription.current_period_start:
                subscription.current_period_start = timezone.now()
        subscription.save()
        messages.success(self.request, "Assinatura salva com sucesso.")
        return redirect(self.success_url)


class HomecareSubscriptionUpdateView(FormContextMixin, HomecareAdminAccessMixin, UpdateView):
    model = HomecareSubscription
    form_class = HomecareSubscriptionForm
    template_name = "core/form.html"
    success_url = reverse_lazy("homecare:subscriptions")
    page_title = "Assinatura do canal"
    section_label = "Conteudos"
    back_url_name = "homecare:subscriptions"

    def form_valid(self, form):
        messages.success(self.request, "Assinatura atualizada com sucesso.")
        return super().form_valid(form)


class HomecarePaymentEventListView(HomecareAdminAccessMixin, SearchableListView, ListView):
    model = HomecarePaymentEvent
    template_name = "homecare/payment_event_list.html"
    context_object_name = "events"
    paginate_by = 20
    search_fields = ["event_id", "event_type", "provider_payment_id", "provider_subscription_id", "external_reference"]

    def get_queryset(self):
        return super().get_queryset().select_related("subscription__patient", "finance_charge")


class HomecarePublicEnabledMixin:
    def dispatch(self, request, *args, **kwargs):
        if not homecare_public_enabled():
            raise Http404("Portal Fisioterapia em Casa indisponivel.")
        return super().dispatch(request, *args, **kwargs)


class HomecarePortalLandingView(HomecarePublicEnabledMixin, TemplateView):
    template_name = "homecare/public_landing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        plans = HomecarePlan.objects.filter(active=True, public_checkout_enabled=True)
        categories = HomecareCategory.objects.filter(active=True).annotate(
            video_total=Count("videos", filter=public_video_q("videos__"))
        )
        context.update(
            {
                "plans": plans,
                "categories": categories,
                "subscription": active_subscription_for_user(self.request.user)
                if self.request.user.is_authenticated
                else None,
                "has_included_access": included_homecare_access_for_user(self.request.user),
            }
        )
        return context


class HomecarePortalAccessMixin(HomecarePublicEnabledMixin, LoginRequiredMixin):
    login_url = "/login/"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.subscription = active_subscription_for_user(request.user)
        self.has_included_access = included_homecare_access_for_user(request.user)
        if not (self.subscription or self.has_included_access):
            return redirect("homecare_public:access_required")
        return super().dispatch(request, *args, **kwargs)


class HomecareAccessRequiredView(HomecarePublicEnabledMixin, LoginRequiredMixin, TemplateView):
    login_url = "/login/"
    template_name = "homecare/access_required.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["plans"] = HomecarePlan.objects.filter(active=True, public_checkout_enabled=True)
        context["has_included_access"] = included_homecare_access_for_user(self.request.user)
        return context


class HomecareLibraryView(HomecarePortalAccessMixin, ListView):
    model = HomecareVideo
    template_name = "homecare/library.html"
    context_object_name = "videos"

    def get_queryset(self):
        queryset = HomecareVideo.objects.select_related("category", "author").filter(public_video_q())
        category_slug = self.kwargs.get("category_slug") or self.request.GET.get("categoria", "")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(category__name__icontains=query)
                | Q(author__full_name__icontains=query)
            )
        difficulty = self.request.GET.get("nivel", "")
        if difficulty in HomecareVideo.Difficulty.values:
            queryset = queryset.filter(difficulty=difficulty)
        duration = self.request.GET.get("duracao", "")
        if duration == "short":
            queryset = queryset.filter(duration_seconds__gt=0, duration_seconds__lte=900)
        elif duration == "medium":
            queryset = queryset.filter(duration_seconds__gt=900, duration_seconds__lte=1500)
        elif duration == "long":
            queryset = queryset.filter(duration_seconds__gt=1500)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_category = self.kwargs.get("category_slug") or self.request.GET.get("categoria", "")
        profile = get_profile(self.request.user)
        video_list = list(context["videos"])
        if profile and profile.patient_id and video_list:
            progress_by_video = {
                progress.video_id: progress
                for progress in HomecareVideoProgress.objects.filter(
                    patient=profile.patient,
                    video_id__in=[video.pk for video in video_list],
                )
            }
            for video in video_list:
                progress = progress_by_video.get(video.pk)
                video.viewer_progress = progress
                video.viewer_progress_percent = self.progress_percent(progress, video)
            context["videos"] = video_list
        continue_watching = []
        if profile and profile.patient_id:
            continue_watching = list(
                HomecareVideoProgress.objects.select_related("video", "video__category", "video__author")
                .filter(public_video_q("video__"), patient=profile.patient)
                .order_by("-last_watched_at")[:3]
            )
            for progress in continue_watching:
                progress.progress_percent = self.progress_percent(progress, progress.video)
        context.update(
            {
                "categories": HomecareCategory.objects.filter(active=True).annotate(
                    video_total=Count("videos", filter=public_video_q("videos__"))
                ),
                "available_video_count": HomecareVideo.objects.filter(public_video_q()).count(),
                "filtered_video_count": len(video_list),
                "subscription": self.subscription,
                "has_included_access": self.has_included_access,
                "selected_category": selected_category,
                "selected_query": self.request.GET.get("q", "").strip(),
                "selected_difficulty": self.request.GET.get("nivel", ""),
                "selected_duration": self.request.GET.get("duracao", ""),
                "difficulty_choices": HomecareVideo.Difficulty.choices,
                "duration_choices": [
                    ("short", "Ate 15 min"),
                    ("medium", "15 a 25 min"),
                    ("long", "Mais de 25 min"),
                ],
                "continue_watching": continue_watching,
                "clear_filters_url": reverse("homecare_public:category", args=[selected_category])
                if selected_category
                else reverse("homecare_public:library"),
            }
        )
        return context

    @staticmethod
    def progress_percent(progress, video):
        if not progress:
            return 0
        if progress.completed:
            return 100
        if not video.duration_seconds:
            return 12
        return max(8, min(98, round((progress.watched_seconds / video.duration_seconds) * 100)))


class HomecareVideoDetailView(HomecarePortalAccessMixin, DetailView):
    model = HomecareVideo
    template_name = "homecare/video_detail.html"
    context_object_name = "video"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return HomecareVideo.objects.select_related("category", "author").filter(public_video_q())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        video = self.object
        profile = get_profile(self.request.user)
        progress = None
        if profile and profile.patient_id:
            progress, _ = HomecareVideoProgress.objects.get_or_create(patient=profile.patient, video=video)
            progress.last_watched_at = timezone.now()
            progress.save(update_fields=["last_watched_at", "updated_at"])
        embed_url = build_bunny_embed_url(video)
        provider_video_id = video.provider_video_id or ""
        is_demo_player = provider_video_id.startswith(("dry-run-", "demo-"))
        replies = (
            HomecareVideoComment.objects.filter(is_active=True)
            .select_related("author", "author__profile")
            .order_by("created_at")
        )
        comments = list(
            HomecareVideoComment.objects.filter(video=video, is_active=True, parent__isnull=True)
            .select_related("author", "author__profile")
            .prefetch_related(Prefetch("replies", queryset=replies, to_attr="active_replies"))
            .order_by("created_at")
        )
        context.update(
            {
                "embed_url": embed_url,
                "is_demo_player": is_demo_player,
                "subscription": self.subscription,
                "progress": progress,
                "likes_total": video.likes.count(),
                "comments_total": HomecareVideoComment.objects.filter(video=video, is_active=True).count(),
                "user_has_liked": HomecareVideoLike.objects.filter(video=video, user=self.request.user).exists(),
                "comments": comments,
                "comment_form": HomecareVideoCommentForm(),
            }
        )
        return context


class HomecareVideoLikeToggleView(HomecarePortalAccessMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, slug):
        video = get_object_or_404(HomecareVideo.objects.filter(public_video_q()), slug=slug)
        like = HomecareVideoLike.objects.filter(video=video, user=request.user).first()
        if like:
            like.delete()
            messages.success(request, "Curtida removida.")
        else:
            HomecareVideoLike.objects.create(video=video, user=request.user)
            messages.success(request, "Aula curtida.")
        return redirect("homecare_public:video_detail", slug=video.slug)


class HomecareVideoCommentCreateView(HomecarePortalAccessMixin, View):
    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, slug):
        video = get_object_or_404(HomecareVideo.objects.filter(public_video_q()), slug=slug)
        form = HomecareVideoCommentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Nao foi possivel publicar o comentario.")
            return redirect(f"{reverse('homecare_public:video_detail', args=[video.slug])}#comentarios")

        parent = None
        parent_id = request.POST.get("parent_id", "").strip()
        if parent_id:
            parent = HomecareVideoComment.objects.filter(
                video=video,
                is_active=True,
                parent__isnull=True,
                pk=parent_id,
            ).first()
            if not parent:
                messages.error(request, "Nao foi possivel encontrar o comentario respondido.")
                return redirect(f"{reverse('homecare_public:video_detail', args=[video.slug])}#comentarios")

        comment = form.save(commit=False)
        comment.video = video
        comment.author = request.user
        comment.parent = parent
        try:
            comment.full_clean()
        except ValidationError:
            messages.error(request, "Nao foi possivel publicar a resposta.")
            return redirect(f"{reverse('homecare_public:video_detail', args=[video.slug])}#comentarios")
        comment.save()
        messages.success(request, "Comentario publicado.")
        return redirect(f"{reverse('homecare_public:video_detail', args=[video.slug])}#comentarios")


class HomecareSubscribeView(HomecarePublicEnabledMixin, LoginRequiredMixin, View):
    login_url = "/login/"

    def post(self, request, slug):
        if not homecare_checkout_enabled():
            messages.error(request, "Assinatura online ainda nao liberada. Solicite a liberacao manual pela clinica.")
            return redirect("homecare_public:access_required")
        plan = get_object_or_404(HomecarePlan, slug=slug, active=True, public_checkout_enabled=True)
        profile = get_profile(request.user)
        if not profile or not profile.is_patient or not profile.patient_id or not profile.patient.active:
            messages.error(request, "A assinatura precisa estar vinculada a um paciente ativo cadastrado.")
            return redirect("homecare_public:access_required")
        subscription = HomecareSubscription.objects.create(
            patient=profile.patient,
            plan=plan,
            status=HomecareSubscription.Status.PENDING,
            source=HomecareSubscription.Source.CHECKOUT,
            provider=HomecareSubscription.Provider.ASAAS,
        )
        try:
            start_checkout_subscription(subscription)
        except IntegrationError as exc:
            subscription.notes = f"Falha ao iniciar checkout: {exc}"
            subscription.save(update_fields=["notes", "updated_at"])
            messages.error(request, str(exc))
            return redirect("homecare_public:access_required")
        if subscription.checkout_url:
            return redirect(subscription.checkout_url)
        messages.success(request, "Assinatura criada. Aguarde a confirmacao do pagamento.")
        return redirect("homecare_public:subscription_status", reference=subscription.external_reference)


class HomecareSubscriptionStatusView(HomecarePublicEnabledMixin, LoginRequiredMixin, DetailView):
    login_url = "/login/"
    model = HomecareSubscription
    template_name = "homecare/subscription_status.html"
    context_object_name = "subscription"
    slug_field = "external_reference"
    slug_url_kwarg = "reference"

    def get_queryset(self):
        profile = get_profile(self.request.user)
        queryset = HomecareSubscription.objects.select_related("patient", "plan")
        if not profile or not profile.is_patient or not profile.patient_id:
            return queryset.none()
        return queryset.filter(patient=profile.patient)


@method_decorator(csrf_exempt, name="dispatch")
class HomecareAsaasWebhookView(View):
    def post(self, request):
        if not homecare_webhook_enabled():
            return JsonResponse({"ok": False, "detail": "Modulo indisponivel."}, status=404)
        provider = get_payment_provider()
        try:
            payload, token_valid = provider.parse_webhook(request)
            event, created = record_asaas_webhook(payload, token_valid)
        except IntegrationError as exc:
            return JsonResponse({"ok": False, "detail": str(exc)}, status=400)
        return JsonResponse({"ok": True, "created": created, "event": event.event_id})
