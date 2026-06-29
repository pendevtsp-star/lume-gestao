from django.urls import path

from homecare.views import (
    HomecareAccessRequiredView,
    HomecareLibraryView,
    HomecarePortalLandingView,
    HomecareSubscribeView,
    HomecareSubscriptionStatusView,
    HomecareVideoCommentCreateView,
    HomecareVideoDetailView,
    HomecareVideoLikeToggleView,
    HomecareVideoStreamView,
)

app_name = "homecare_public"

urlpatterns = [
    path("", HomecarePortalLandingView.as_view(), name="landing"),
    path("sem-acesso/", HomecareAccessRequiredView.as_view(), name="access_required"),
    path("biblioteca/", HomecareLibraryView.as_view(), name="library"),
    path("biblioteca/categoria/<slug:category_slug>/", HomecareLibraryView.as_view(), name="category"),
    path("videos/<slug:slug>/", HomecareVideoDetailView.as_view(), name="video_detail"),
    path("videos/<slug:slug>/assistir/", HomecareVideoStreamView.as_view(), name="video_stream"),
    path("videos/<slug:slug>/curtir/", HomecareVideoLikeToggleView.as_view(), name="toggle_like"),
    path("videos/<slug:slug>/comentarios/", HomecareVideoCommentCreateView.as_view(), name="add_comment"),
    path("assinar/<slug:slug>/", HomecareSubscribeView.as_view(), name="subscribe"),
    path("assinatura/<slug:reference>/", HomecareSubscriptionStatusView.as_view(), name="subscription_status"),
]
