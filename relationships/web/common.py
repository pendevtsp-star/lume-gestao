from accounts.models import UserProfile
from accounts.permissions import RoleRequiredMixin


class RelationshipAccessMixin(RoleRequiredMixin):
    allowed_roles = [
        UserProfile.Role.ADMINISTRATION,
        UserProfile.Role.MANAGEMENT,
    ]
