from django.urls import path

from accounts.views import (
    ForcePasswordChangeView,
    UserAccountCreateView,
    UserAccountDeleteView,
    UserAccountListView,
    UserAccountUpdateView,
    UserSelfSettingsView,
)

app_name = "accounts"

urlpatterns = [
    path("minha-conta/", UserSelfSettingsView.as_view(), name="self_settings"),
    path("primeiro-acesso/", ForcePasswordChangeView.as_view(), name="force_password_change"),
    path("", UserAccountListView.as_view(), name="list"),
    path("novo/", UserAccountCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", UserAccountUpdateView.as_view(), name="update"),
    path("<int:pk>/excluir/", UserAccountDeleteView.as_view(), name="delete"),
]
