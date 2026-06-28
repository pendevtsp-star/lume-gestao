from django.urls import include, path

urlpatterns = [
    path("", include("website.public_urls")),
]
