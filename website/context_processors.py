from django.conf import settings
from urllib.parse import urlparse


def website_urls(_request):
    system_host = urlparse(settings.SYSTEM_BASE_URL).hostname if settings.SYSTEM_BASE_URL else ""
    return {
        "website_base_url": settings.WEBSITE_BASE_URL,
        "system_base_url": settings.SYSTEM_BASE_URL,
        "system_host_label": system_host or "Lume local",
    }
