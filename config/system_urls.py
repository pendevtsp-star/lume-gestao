from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.utils.cache import add_never_cache_headers
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from accounts.api import UserProfileViewSet
from accounts.views import PasswordRecoveryRequestView
from billing.api import (
    ChargeViewSet,
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    MembershipViewSet,
    PaymentViewSet,
    ServicePlanViewSet,
)
from patients.api import PatientViewSet, ProfessionalNoteViewSet, ProfessionalPatientAssignmentViewSet
from scheduling.api import (
    AppointmentViewSet,
    ProfessionalAvailabilityViewSet,
    ServicePackageViewSet,
    ServiceUsageViewSet,
)
from team.api import EmployeeViewSet, ProfessionalViewSet

router = DefaultRouter()
router.register(r"user-profiles", UserProfileViewSet)
router.register(r"patients", PatientViewSet)
router.register(r"patient-professional-assignments", ProfessionalPatientAssignmentViewSet)
router.register(r"professional-notes", ProfessionalNoteViewSet)
router.register(r"employees", EmployeeViewSet)
router.register(r"professionals", ProfessionalViewSet)
router.register(r"plans", ServicePlanViewSet)
router.register(r"memberships", MembershipViewSet)
router.register(r"payments", PaymentViewSet)
router.register(r"expense-categories", ExpenseCategoryViewSet)
router.register(r"expenses", ExpenseViewSet)
router.register(r"charges", ChargeViewSet)
router.register(r"appointments", AppointmentViewSet)
router.register(r"professional-availabilities", ProfessionalAvailabilityViewSet)
router.register(r"service-packages", ServicePackageViewSet)
router.register(r"service-usages", ServiceUsageViewSet)


class PwaTemplateView(TemplateView):
    """Serve installation files fresh so existing PWAs pick up new releases."""

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        add_never_cache_headers(response)
        return response

urlpatterns = [
    path(
        "manifest.webmanifest",
        PwaTemplateView.as_view(template_name="pwa/manifest.webmanifest", content_type="application/manifest+json"),
        name="pwa_manifest",
    ),
    path(
        "sw.js",
        PwaTemplateView.as_view(template_name="pwa/sw.js", content_type="application/javascript"),
        name="pwa_service_worker",
    ),
    path("", include("core.urls")),
    path("usuarios/", include("accounts.urls")),
    path("pacientes/", include("patients.urls")),
    path("equipe/", include("team.urls")),
    path("financeiro/", include("billing.urls")),
    path("agenda/", include("scheduling.urls")),
    path("relatorios/", include("reports.urls")),
    path("fiscal/", include("fiscal.urls")),
    path("site/", include("website.urls")),
    path("conteudos/", include("homecare.urls")),
    path("pilates-em-casa/", include("homecare.public_urls")),
    path("checkout/", include("checkout.urls")),
    path("lume-connect/", include("lume_connect.urls")),
    path("api/v1/mobile/auth/token/", obtain_auth_token, name="mobile_auth_token"),
    path("api/v1/mobile/", include("mobile.urls")),
    path("api/v1/", include(router.urls)),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("recuperar-senha/", PasswordRecoveryRequestView.as_view(), name="password_reset"),
    path("recuperar-senha/enviado/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "recuperar-senha/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("recuperar-senha/concluido/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
