from django.conf import settings
from urllib.parse import urlparse


def website_urls(_request):
    system_host = urlparse(settings.SYSTEM_BASE_URL).hostname if settings.SYSTEM_BASE_URL else ""
    return {
        "website_base_url": settings.WEBSITE_BASE_URL,
        "system_base_url": settings.SYSTEM_BASE_URL,
        "system_host_label": system_host or "Lume local",
        "app_version": settings.APP_VERSION,
        "checkout_enabled": settings.CHECKOUT_ENABLED,
        "checkout_public_enabled": settings.CHECKOUT_ENABLED and settings.CHECKOUT_PUBLIC_ENABLED,
        "checkout_patient_enabled": settings.CHECKOUT_ENABLED and settings.CHECKOUT_PATIENT_ENABLED,
    }
