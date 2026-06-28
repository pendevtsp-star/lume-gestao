from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect

from accounts.models import UserProfile

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_profile(user):
    if not user.is_authenticated:
        return None
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def has_role(user, roles):
    if user.is_superuser:
        return True
    profile = get_profile(user)
    return bool(profile and profile.role in roles)


class RoleRequiredMixin(AccessMixin):
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        profile = get_profile(request.user)
        if profile and profile.role == UserProfile.Role.VIEWER and request.method in SAFE_METHODS:
            return super().dispatch(request, *args, **kwargs)
        if not has_role(request.user, set(self.allowed_roles)):
            messages.error(request, "Seu perfil nao tem permissao para acessar esta area.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class FinanceAccessMixin(RoleRequiredMixin):
    allowed_roles = [UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT]


class ManagementAccessMixin(RoleRequiredMixin):
    allowed_roles = [UserProfile.Role.MANAGEMENT]
