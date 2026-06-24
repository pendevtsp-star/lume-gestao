from django.urls import path

from core.views import DashboardView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
]
