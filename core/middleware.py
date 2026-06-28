from django.http import HttpResponseForbidden

from accounts.models import UserProfile
from core.audit import set_current_user


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
READ_ONLY_ALLOWED_PATHS = ("/logout/",)


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        if user and request.method in UNSAFE_METHODS and not request.path_info.startswith(READ_ONLY_ALLOWED_PATHS):
            profile = getattr(user, "profile", None)
            if profile and profile.role == UserProfile.Role.VIEWER:
                return HttpResponseForbidden("Usuario de visualizacao nao pode alterar dados.")
        set_current_user(user)
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)
