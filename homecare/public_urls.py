from django.urls import path

from homecare.views import (
    HomecareAccessRequiredView,
    HomecareLibraryView,
    HomecarePortalLandingView,
    HomecareSubscribeView,
    HomecareSubscriptionStatusView,
    HomecareVideoDetailView,
)

app_name = "homecare_public"

urlpatterns = [
    path("", HomecarePortalLandingView.as_view(), name="landing"),
    path("sem-acesso/", HomecareAccessRequiredView.as_view(), name="access_required"),
    path("biblioteca/", HomecareLibraryView.as_view(), name="library"),
    path("biblioteca/categoria/<slug:category_slug>/", HomecareLibraryView.as_view(), name="category"),
    path("videos/<slug:slug>/", HomecareVideoDetailView.as_view(), name="video_detail"),
    path("assinar/<slug:slug>/", HomecareSubscribeView.as_view(), name="subscribe"),
    path("assinatura/<slug:reference>/", HomecareSubscriptionStatusView.as_view(), name="subscription_status"),
]
