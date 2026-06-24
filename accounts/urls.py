from django.urls import path

from accounts.views import UserAccountCreateView, UserAccountListView, UserAccountUpdateView

app_name = "accounts"

urlpatterns = [
    path("", UserAccountListView.as_view(), name="list"),
    path("novo/", UserAccountCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", UserAccountUpdateView.as_view(), name="update"),
]
