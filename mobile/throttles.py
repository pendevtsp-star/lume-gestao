from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class MobileLoginRateThrottle(SimpleRateThrottle):
    scope = "mobile_login"

    def get_rate(self):
        return getattr(settings, "MOBILE_LOGIN_THROTTLE_RATE", "10/min")

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
