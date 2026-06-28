from django.urls import path

from mobile.views import (
    MobileAgendaView,
    MobileBootstrapView,
    MobileCreditsView,
    MobileLoginView,
    MobileLogoutView,
    MobilePatientsView,
    MobilePaymentsView,
    MobileProfessionalNotesView,
    MobileProfileView,
)

app_name = "mobile"

urlpatterns = [
    path("auth/login/", MobileLoginView.as_view(), name="login"),
    path("auth/logout/", MobileLogoutView.as_view(), name="logout"),
    path("bootstrap/", MobileBootstrapView.as_view(), name="bootstrap"),
    path("profile/", MobileProfileView.as_view(), name="profile"),
    path("agenda/", MobileAgendaView.as_view(), name="agenda"),
    path("credits/", MobileCreditsView.as_view(), name="credits"),
    path("payments/", MobilePaymentsView.as_view(), name="payments"),
    path("patients/", MobilePatientsView.as_view(), name="patients"),
    path("professional-notes/", MobileProfessionalNotesView.as_view(), name="professional_notes"),
]
