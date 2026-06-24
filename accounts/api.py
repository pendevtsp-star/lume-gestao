from rest_framework.viewsets import ModelViewSet

from accounts.models import UserProfile
from accounts.serializers import UserProfileSerializer
from core.api_permissions import ManagementApiPermission


class UserProfileViewSet(ModelViewSet):
    queryset = UserProfile.objects.select_related("user", "patient", "professional")
    serializer_class = UserProfileSerializer
    permission_classes = [ManagementApiPermission]
    filterset_fields = ["role"]
    search_fields = ["user__username", "user__email", "patient__full_name", "professional__full_name"]
    ordering_fields = ["user__username", "created_at"]
