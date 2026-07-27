import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

from core.integrations.http import IntegrationError, post_json


BASE_DIR = Path(__file__).resolve().parent.parent


class ProductionCookieDefaultsTests(SimpleTestCase):
    def test_cookie_policy_can_be_overridden_by_environment(self):
        env = os.environ.copy()
        env.update(
            {
                "DEBUG": "True",
                "ENVIRONMENT": "development",
                "LUME_STRICT_PRODUCTION": "False",
                "DB_ENGINE": "sqlite",
                "SESSION_COOKIE_HTTPONLY": "False",
                "SESSION_COOKIE_SAMESITE": "Strict",
                "CSRF_COOKIE_SAMESITE": "Strict",
            }
        )
        script = (
            "import json; "
            "from config import settings; "
            "print(json.dumps({"
            "'session_httponly': settings.SESSION_COOKIE_HTTPONLY, "
            "'session_samesite': settings.SESSION_COOKIE_SAMESITE, "
            "'csrf_samesite': settings.CSRF_COOKIE_SAMESITE"
            "}))"
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=BASE_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            json.loads(result.stdout.strip()),
            {
                "session_httponly": False,
                "session_samesite": "Strict",
                "csrf_samesite": "Strict",
            },
        )


class PwaSecurityContractTests(SimpleTestCase):
    def test_service_worker_only_cache_firsts_versioned_static_assets(self):
        response = self.client.get(reverse("pwa_service_worker"))
        source = response.content.decode("utf-8")

        self.assertContains(response, "isVersionedStaticAsset")
        self.assertContains(response, 'url.pathname.startsWith("/static/")')
        self.assertContains(response, 'url.searchParams.has("v")')
        self.assertNotIn('if (url.pathname.startsWith("/static/"))', source)
        self.assertNotIn("cache.put(request", source)

    def test_service_worker_does_not_cache_navigation_or_api_responses(self):
        response = self.client.get(reverse("pwa_service_worker"))
        source = response.content.decode("utf-8")

        self.assertIn('request.mode === "navigate"', source)
        self.assertNotIn('caches.open(LUME_CACHE).then((cache) => cache.put(request', source)
        self.assertNotIn('url.pathname.startsWith("/api/")', source)

    def test_manifest_has_stable_identity_and_language(self):
        response = self.client.get(reverse("pwa_manifest"))
        manifest = json.loads(response.content)

        self.assertEqual(manifest["id"], "/")
        self.assertEqual(manifest["lang"], "pt-BR")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        sizes = {icon["sizes"] for icon in manifest["icons"]}
        self.assertTrue({"192x192", "512x512"}.issubset(sizes))

    def test_pwa_files_are_served_with_no_store_policy(self):
        for route_name in ("pwa_manifest", "pwa_service_worker"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                cache_control = response.headers.get("Cache-Control", "")
                self.assertIn("no-store", cache_control)


class OutboundHttpSecurityTests(SimpleTestCase):
    def test_generic_json_client_rejects_non_http_urls(self):
        with self.assertRaisesMessage(
            IntegrationError,
            "A integracao aceita apenas URLs HTTP ou HTTPS validas.",
        ):
            post_json("file:///tmp/lume-sensitive.txt", {"value": "blocked"})
