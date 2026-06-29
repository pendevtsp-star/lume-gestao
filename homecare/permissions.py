from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect

from accounts.models import UserProfile
from accounts.permissions import get_profile
from homecare.features import homecare_internal_enabled


HOMECARE_CONTENT_ROLES = {
    UserProfile.Role.PROFESSIONAL,
    UserProfile.Role.ADMINISTRATION,
    UserProfile.Role.MANAGEMENT,
}

HOMECARE_ADMIN_ROLES = {
    UserProfile.Role.ADMINISTRATION,
    UserProfile.Role.MANAGEMENT,
}


def can_manage_homecare_content(user):
    if user.is_superuser:
        return True
    profile = get_profile(user)
    return bool(profile and profile.role in HOMECARE_CONTENT_ROLES)


def can_manage_homecare_settings(user):
    if user.is_superuser:
        return True
    profile = get_profile(user)
    return bool(profile and profile.role in HOMECARE_ADMIN_ROLES)


class HomecareContentAccessMixin(LoginRequiredMixin, AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not homecare_internal_enabled():
            raise Http404("Modulo Fisioterapia em Casa indisponivel.")
        if not can_manage_homecare_content(request.user):
            messages.error(request, "Seu perfil nao tem permissao para gerenciar conteudos.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class HomecareAdminAccessMixin(LoginRequiredMixin, AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not homecare_internal_enabled():
            raise Http404("Modulo Fisioterapia em Casa indisponivel.")
        if not can_manage_homecare_settings(request.user):
            messages.error(request, "Seu perfil nao tem permissao para configurar o canal.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)
