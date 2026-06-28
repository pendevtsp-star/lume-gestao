from django.urls import path

from website.views import (
    WebsiteDashboardView,
    WebsiteFAQCreateView,
    WebsiteFAQDeleteView,
    WebsiteFAQListView,
    WebsiteFAQUpdateView,
    WebsiteSettingsUpdateView,
    WebsiteTestimonialCreateView,
    WebsiteTestimonialDeleteView,
    WebsiteTestimonialListView,
    WebsiteTestimonialUpdateView,
)

app_name = "website"

urlpatterns = [
    path("", WebsiteDashboardView.as_view(), name="dashboard"),
    path("configuracoes/", WebsiteSettingsUpdateView.as_view(), name="settings"),
    path("faqs/", WebsiteFAQListView.as_view(), name="faqs"),
    path("faqs/novo/", WebsiteFAQCreateView.as_view(), name="faq_create"),
    path("faqs/<int:pk>/editar/", WebsiteFAQUpdateView.as_view(), name="faq_update"),
    path("faqs/<int:pk>/excluir/", WebsiteFAQDeleteView.as_view(), name="faq_delete"),
    path("depoimentos/", WebsiteTestimonialListView.as_view(), name="testimonials"),
    path("depoimentos/novo/", WebsiteTestimonialCreateView.as_view(), name="testimonial_create"),
    path("depoimentos/<int:pk>/editar/", WebsiteTestimonialUpdateView.as_view(), name="testimonial_update"),
    path("depoimentos/<int:pk>/excluir/", WebsiteTestimonialDeleteView.as_view(), name="testimonial_delete"),
]

