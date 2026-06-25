from django.urls import path

from accounts.views import UserAccountCreateView, UserAccountListView, UserAccountUpdateView, UserSelfSettingsView

app_name = "accounts"

urlpatterns = [
    path("minha-conta/", UserSelfSettingsView.as_view(), name="self_settings"),
    path("", UserAccountListView.as_view(), name="list"),
    path("novo/", UserAccountCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", UserAccountUpdateView.as_view(), name="update"),
]
