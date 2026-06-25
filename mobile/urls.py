from django.urls import path

from mobile.views import MobileBootstrapView

app_name = "mobile"

urlpatterns = [
    path("bootstrap/", MobileBootstrapView.as_view(), name="bootstrap"),
]
