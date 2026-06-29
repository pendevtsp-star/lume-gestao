import json
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView, View

from accounts.permissions import ManagementAccessMixin
from billing.models import ServicePlan
from core.views import FormContextMixin, SearchableListView
from core.models import ClinicSettings
from website.content import INSTAGRAM_HIGHLIGHTS, REEL_FEATURES
from website.forms import WebsiteFAQForm, WebsiteSettingsForm, WebsiteTestimonialForm
from website.models import WebsiteFAQ, WebsiteSettings, WebsiteTestimonial


class WebsitePublicContextMixin:
    service_cards = [
        {
            "title": "Pilates",
            "description": "Aulas com foco em postura, fortalecimento, respiração e consciência corporal.",
        },
        {
            "title": "Fisioterapia",
            "description": "Reabilitação individualizada para dor, lesões, limitações funcionais e prevenção.",
        },
        {
            "title": "Massagem",
            "description": "Alívio muscular e relaxamento para renovar energia e bem-estar.",
        },
        {
            "title": "Reiki",
            "description": "Um cuidado complementar para equilíbrio, relaxamento e reconexão.",
        },
    ]
    journey_steps = [
        "Você entra em contato pelo WhatsApp e conta seu objetivo ou necessidade.",
        "Nossa equipe orienta o melhor atendimento, plano ou combinação de serviços.",
        "Você agenda com rapidez e inicia um cuidado contínuo com acompanhamento humano.",
    ]
    quick_benefits = [
        "Atendimento acolhedor",
        "Agendamento pelo WhatsApp",
        "Studio em Penedo/AL",
    ]

    def build_canonical_url(self, path):
        base_url = settings.WEBSITE_BASE_URL.rstrip("/")
        if base_url:
            return f"{base_url}{path}"
        return self.request.build_absolute_uri(path)

    def build_structured_data(self, website_settings, faqs):
        contact_phone = ClinicSettings.load().phone or ""
        business_schema = {
            "@type": "MedicalBusiness",
            "name": website_settings.resolved_clinic_name,
            "description": website_settings.seo_description,
            "url": self.build_canonical_url("/"),
            "address": {
                "@type": "PostalAddress",
                "streetAddress": website_settings.resolved_address,
                "addressLocality": website_settings.city_name,
                "addressCountry": "BR",
            },
            "sameAs": [website_settings.resolved_instagram_url],
            "contactPoint": [
                {
                    "@type": "ContactPoint",
                    "contactType": "customer support",
                    "url": website_settings.resolved_whatsapp_url,
                }
            ],
        }
        if contact_phone:
            business_schema["telephone"] = contact_phone
        graph = [business_schema]
        if faqs:
            graph.append(
                {
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": faq.question,
                            "acceptedAnswer": {"@type": "Answer", "text": faq.answer},
                        }
                        for faq in faqs
                    ],
                }
            )
        return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)


class WebsiteHomeView(WebsitePublicContextMixin, TemplateView):
    template_name = "website/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        website_settings = WebsiteSettings.load()
        plans = list(
            ServicePlan.objects.filter(active=True, show_on_website=True).order_by(
                "display_order", "monthly_price", "name"
            )[:4]
        )
        faqs = list(WebsiteFAQ.objects.filter(active=True)[:6])
        testimonials = list(WebsiteTestimonial.objects.filter(active=True)[:3])
        assistant_questions = [faq.question for faq in faqs[:3]] or [
            "Quais atendimentos vocês oferecem?",
            "Como faço para agendar?",
            "Como funcionam os planos?",
        ]
        assistant_answers = {faq.question: faq.answer for faq in faqs}
        context.update(
            {
                "website_settings": website_settings,
                "page_title": website_settings.seo_title,
                "browser_title": f"{website_settings.resolved_clinic_name} | Lume Gestao",
                "meta_description": website_settings.seo_description,
                "canonical_url": self.build_canonical_url(self.request.path),
                "plans": plans,
                "service_cards": self.service_cards,
                "journey_steps": self.journey_steps,
                "quick_benefits": self.quick_benefits,
                "faqs": faqs,
                "testimonials": testimonials,
                "assistant_questions": assistant_questions,
                "assistant_faq_map_json": assistant_answers,
                "reel_features": REEL_FEATURES,
                "instagram_highlights": INSTAGRAM_HIGHLIGHTS,
                "structured_data_json": self.build_structured_data(website_settings, faqs),
                "current_year": date.today().year,
            }
        )
        return context


class WebsiteRobotsTxtView(View):
    def get(self, request):
        base_url = settings.WEBSITE_BASE_URL.rstrip("/") or request.build_absolute_uri("/").rstrip("/")
        body = f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n"
        return HttpResponse(body, content_type="text/plain; charset=utf-8")


class WebsiteSitemapView(View):
    def get(self, request):
        home_url = (settings.WEBSITE_BASE_URL.rstrip("/") or request.build_absolute_uri("/").rstrip("/")) + "/"
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{home_url}</loc></url>"
            "</urlset>"
        )
        return HttpResponse(body, content_type="application/xml; charset=utf-8")


class WebsiteTrackedRedirectView(View):
    counter_field = ""

    def get_target_url(self):
        website_settings = WebsiteSettings.load()
        if self.counter_field == "system_clicks":
            return website_settings.resolved_system_url
        return website_settings.resolved_whatsapp_url

    def get(self, request):
        if self.counter_field:
            WebsiteSettings.objects.filter(pk=WebsiteSettings.load().pk).update(
                **{self.counter_field: F(self.counter_field) + 1}
            )
        return redirect(self.get_target_url())


class WebsiteWhatsAppRedirectView(WebsiteTrackedRedirectView):
    counter_field = "whatsapp_clicks"


class WebsiteSystemRedirectView(WebsiteTrackedRedirectView):
    counter_field = "system_clicks"


class WebsiteInstagramRedirectView(WebsiteTrackedRedirectView):
    counter_field = ""

    def get_target_url(self):
        return WebsiteSettings.load().resolved_instagram_url


class WebsiteDashboardView(ManagementAccessMixin, TemplateView):
    template_name = "website/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        website_settings = WebsiteSettings.load()
        context.update(
            {
                "website_settings": website_settings,
                "page_title": "Site",
                "section_label": "Gerencia",
                "preview_url": settings.WEBSITE_BASE_URL or "https://clinicafisiolume.com.br",
                "public_plan_count": ServicePlan.objects.filter(active=True, show_on_website=True).count(),
                "faq_count": WebsiteFAQ.objects.filter(active=True).count(),
                "testimonial_count": WebsiteTestimonial.objects.filter(active=True).count(),
                "public_plans": ServicePlan.objects.filter(active=True, show_on_website=True).order_by("display_order", "name")[:6],
                "recent_faqs": WebsiteFAQ.objects.all()[:5],
                "recent_testimonials": WebsiteTestimonial.objects.all()[:5],
            }
        )
        return context


class WebsiteSettingsUpdateView(ManagementAccessMixin, UpdateView):
    model = WebsiteSettings
    form_class = WebsiteSettingsForm
    template_name = "core/form.html"
    success_url = reverse_lazy("website:dashboard")

    def get_object(self, queryset=None):
        return WebsiteSettings.load()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Configuracoes do site",
                "section_label": "Site",
                "back_url": reverse("website:dashboard"),
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Configuracoes do site atualizadas com sucesso.")
        return super().form_valid(form)


class WebsiteFAQListView(ManagementAccessMixin, SearchableListView, ListView):
    model = WebsiteFAQ
    template_name = "website/faq_list.html"
    context_object_name = "faqs"
    paginate_by = 12
    search_fields = ["question", "answer"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"active_total": WebsiteFAQ.objects.filter(active=True).count()})
        return context


class WebsiteFAQCreateView(FormContextMixin, ManagementAccessMixin, CreateView):
    model = WebsiteFAQ
    form_class = WebsiteFAQForm
    template_name = "core/form.html"
    success_url = reverse_lazy("website:faqs")
    page_title = "Novo FAQ"
    section_label = "Site"
    back_url_name = "website:faqs"

    def form_valid(self, form):
        messages.success(self.request, "FAQ criado com sucesso.")
        return super().form_valid(form)


class WebsiteFAQUpdateView(FormContextMixin, ManagementAccessMixin, UpdateView):
    model = WebsiteFAQ
    form_class = WebsiteFAQForm
    template_name = "core/form.html"
    success_url = reverse_lazy("website:faqs")
    page_title = "Editar FAQ"
    section_label = "Site"
    back_url_name = "website:faqs"

    def form_valid(self, form):
        messages.success(self.request, "FAQ atualizado com sucesso.")
        return super().form_valid(form)


class WebsiteFAQDeleteView(ManagementAccessMixin, DeleteView):
    model = WebsiteFAQ
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("website:faqs")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Excluir FAQ",
                "section_label": "Site",
                "back_url": reverse("website:faqs"),
                "object_name": self.object.question,
                "entity_label": "FAQ",
                "delete_explanation": "A pergunta sera removida do site imediatamente.",
                "delete_button_label": "Excluir FAQ",
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "FAQ excluido com sucesso.")
        return super().form_valid(form)


class WebsiteTestimonialListView(ManagementAccessMixin, SearchableListView, ListView):
    model = WebsiteTestimonial
    template_name = "website/testimonial_list.html"
    context_object_name = "testimonials"
    paginate_by = 12
    search_fields = ["author_name", "author_role", "body"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"active_total": WebsiteTestimonial.objects.filter(active=True).count()})
        return context


class WebsiteTestimonialCreateView(FormContextMixin, ManagementAccessMixin, CreateView):
    model = WebsiteTestimonial
    form_class = WebsiteTestimonialForm
    template_name = "core/form.html"
    success_url = reverse_lazy("website:testimonials")
    page_title = "Novo depoimento"
    section_label = "Site"
    back_url_name = "website:testimonials"

    def form_valid(self, form):
        messages.success(self.request, "Depoimento criado com sucesso.")
        return super().form_valid(form)


class WebsiteTestimonialUpdateView(FormContextMixin, ManagementAccessMixin, UpdateView):
    model = WebsiteTestimonial
    form_class = WebsiteTestimonialForm
    template_name = "core/form.html"
    success_url = reverse_lazy("website:testimonials")
    page_title = "Editar depoimento"
    section_label = "Site"
    back_url_name = "website:testimonials"

    def form_valid(self, form):
        messages.success(self.request, "Depoimento atualizado com sucesso.")
        return super().form_valid(form)


class WebsiteTestimonialDeleteView(ManagementAccessMixin, DeleteView):
    model = WebsiteTestimonial
    template_name = "core/confirm_deactivate.html"
    success_url = reverse_lazy("website:testimonials")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Excluir depoimento",
                "section_label": "Site",
                "back_url": reverse("website:testimonials"),
                "object_name": self.object.author_name,
                "entity_label": "depoimento",
                "delete_explanation": "Este depoimento deixara de aparecer no site publico.",
                "delete_button_label": "Excluir depoimento",
            }
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, "Depoimento excluido com sucesso.")
        return super().form_valid(form)
