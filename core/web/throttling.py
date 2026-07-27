import hashlib

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse


class FixedWindowRateLimitMixin:
    """Small cache-backed limiter for sensitive non-DRF POST endpoints."""

    rate_limit = 10
    rate_period = 60
    rate_scope = None
    rate_limit_methods = {"POST"}
    rate_limit_json = False

    def dispatch(self, request, *args, **kwargs):
        if self._should_limit(request) and self._increment_and_exceeded(request):
            response_data = "Muitas tentativas. Aguarde e tente novamente."
            if self.rate_limit_json:
                response = JsonResponse({"ok": False, "detail": response_data}, status=429)
            else:
                response = HttpResponse(response_data, status=429)
            response["Retry-After"] = str(self.rate_period)
            return response
        return super().dispatch(request, *args, **kwargs)

    def _should_limit(self, request):
        return bool(
            getattr(settings, "LUME_RATE_LIMIT_ENABLED", True)
            and request.method.upper() in self.rate_limit_methods
        )

    def _increment_and_exceeded(self, request):
        scope = self.rate_scope or f"{self.__class__.__module__}.{self.__class__.__name__}"
        identity = self._request_identity(request)
        digest = hashlib.sha256(f"{scope}:{identity}".encode("utf-8")).hexdigest()
        key = f"lume-rate-limit:{digest}"
        if cache.add(key, 1, timeout=self.rate_period):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=self.rate_period)
                count = 1
        return count > self.rate_limit

    @staticmethod
    def _request_identity(request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return f"user:{user.pk}"
        return f"ip:{request.META.get('REMOTE_ADDR') or 'unknown'}"
