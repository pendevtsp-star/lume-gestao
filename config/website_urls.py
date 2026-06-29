from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.views import PasswordRecoveryRequestView
from core.views import LegalDocumentView

urlpatterns = [
    path("", include("website.public_urls")),
    path("checkout/", include("checkout.urls")),
    path(
        "login/",
        auth_views.LoginView.as_view(next_page="/"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="/"), name="logout"),
    path("recuperar-senha/", PasswordRecoveryRequestView.as_view(), name="password_reset"),
    path("recuperar-senha/enviado/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "recuperar-senha/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("recuperar-senha/concluido/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("termos-de-uso/", LegalDocumentView.as_view(document_key="terms"), name="terms_of_use"),
    path("privacidade/", LegalDocumentView.as_view(document_key="privacy"), name="privacy_policy"),
    path("consentimento-lgpd/", LegalDocumentView.as_view(document_key="sensitive"), name="sensitive_data_consent"),
]
