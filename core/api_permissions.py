from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import UserProfile
from accounts.permissions import get_profile, is_read_only_viewer_request


class RoleApiPermission(BasePermission):
    allowed_roles = set()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        if is_read_only_viewer_request(request.user, request.method):
            return True
        profile = get_profile(request.user)
        if profile and profile.role == UserProfile.Role.VIEWER:
            return request.method in SAFE_METHODS
        return bool(profile and profile.role in self.allowed_roles)


class ManagementApiPermission(RoleApiPermission):
    allowed_roles = {UserProfile.Role.MANAGEMENT}


class FinanceApiPermission(RoleApiPermission):
    allowed_roles = {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT}


class ProfessionalApiPermission(RoleApiPermission):
    allowed_roles = {UserProfile.Role.PROFESSIONAL}


class ClinicApiPermission(RoleApiPermission):
    allowed_roles = {
        UserProfile.Role.PATIENT,
        UserProfile.Role.PROFESSIONAL,
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
        UserProfile.Role.VIEWER,
    }
