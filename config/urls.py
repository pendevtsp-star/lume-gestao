"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounts.api import UserProfileViewSet
from billing.api import ChargeViewSet, ExpenseViewSet, MembershipViewSet, PaymentViewSet, ServicePlanViewSet
from patients.api import PatientViewSet, ProfessionalNoteViewSet, ProfessionalPatientAssignmentViewSet
from scheduling.api import AppointmentViewSet, ServicePackageViewSet, ServiceUsageViewSet
from team.api import EmployeeViewSet, ProfessionalViewSet

router = DefaultRouter()
router.register(r'user-profiles', UserProfileViewSet)
router.register(r'patients', PatientViewSet)
router.register(r'patient-professional-assignments', ProfessionalPatientAssignmentViewSet)
router.register(r'professional-notes', ProfessionalNoteViewSet)
router.register(r'employees', EmployeeViewSet)
router.register(r'professionals', ProfessionalViewSet)
router.register(r'plans', ServicePlanViewSet)
router.register(r'memberships', MembershipViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'expenses', ExpenseViewSet)
router.register(r'charges', ChargeViewSet)
router.register(r'appointments', AppointmentViewSet)
router.register(r'service-packages', ServicePackageViewSet)
router.register(r'service-usages', ServiceUsageViewSet)

urlpatterns = [
    path('', include('core.urls')),
    path('usuarios/', include('accounts.urls')),
    path('pacientes/', include('patients.urls')),
    path('equipe/', include('team.urls')),
    path('financeiro/', include('billing.urls')),
    path('agenda/', include('scheduling.urls')),
    path('api/v1/', include(router.urls)),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('admin/', admin.site.urls),
]
