from django.urls import path

from core.views import HealthCheckView
from website.views import (
    WebsiteHomeView,
    WebsiteInstagramRedirectView,
    WebsiteRobotsTxtView,
    WebsiteSitemapView,
    WebsiteSystemRedirectView,
    WebsiteWhatsAppRedirectView,
)

urlpatterns = [
    path("", WebsiteHomeView.as_view(), name="website_home"),
    path("healthz/", HealthCheckView.as_view(), name="healthz"),
    path("robots.txt", WebsiteRobotsTxtView.as_view(), name="website_robots"),
    path("sitemap.xml", WebsiteSitemapView.as_view(), name="website_sitemap"),
    path("ir/instagram/", WebsiteInstagramRedirectView.as_view(), name="website_instagram_redirect"),
    path("ir/whatsapp/", WebsiteWhatsAppRedirectView.as_view(), name="website_whatsapp_redirect"),
    path("ir/sistema/", WebsiteSystemRedirectView.as_view(), name="website_system_redirect"),
]
