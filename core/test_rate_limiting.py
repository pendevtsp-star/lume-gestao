from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.views import View

from core.web.throttling import FixedWindowRateLimitMixin
from checkout.views import AsaasCheckoutWebhookView, PublicPlanCheckoutView
from homecare.views import HomecareAsaasWebhookView, HomecareVideoCreateView
from lume_connect.views import PostCreateView
from scheduling.web.notifications_events import GenerateNotificationsView


class LimitedView(FixedWindowRateLimitMixin, View):
    rate_limit = 2
    rate_period = 60
    rate_scope = "test-limited-view"

    def post(self, request):
        return HttpResponse("ok")


@override_settings(LUME_RATE_LIMIT_ENABLED=True)
class FixedWindowRateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.view = LimitedView.as_view()

    def tearDown(self):
        cache.clear()

    def test_rejects_request_after_limit_for_same_remote_address(self):
        first = self.view(self.factory.post("/limited/", REMOTE_ADDR="203.0.113.10"))
        second = self.view(self.factory.post("/limited/", REMOTE_ADDR="203.0.113.10"))
        blocked = self.view(self.factory.post("/limited/", REMOTE_ADDR="203.0.113.10"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked["Retry-After"], "60")

    def test_sensitive_views_use_the_shared_rate_limiter(self):
        protected_views = (
            PublicPlanCheckoutView,
            AsaasCheckoutWebhookView,
            HomecareVideoCreateView,
            HomecareAsaasWebhookView,
            PostCreateView,
            GenerateNotificationsView,
        )

        for view_class in protected_views:
            with self.subTest(view=view_class.__name__):
                self.assertTrue(issubclass(view_class, FixedWindowRateLimitMixin))

    def test_does_not_use_untrusted_forwarded_for_header_as_identity(self):
        first = self.view(
            self.factory.post(
                "/limited/",
                REMOTE_ADDR="203.0.113.20",
                HTTP_X_FORWARDED_FOR="198.51.100.1",
            )
        )
        second = self.view(
            self.factory.post(
                "/limited/",
                REMOTE_ADDR="203.0.113.20",
                HTTP_X_FORWARDED_FOR="198.51.100.2",
            )
        )
        blocked = self.view(
            self.factory.post(
                "/limited/",
                REMOTE_ADDR="203.0.113.20",
                HTTP_X_FORWARDED_FOR="198.51.100.3",
            )
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
