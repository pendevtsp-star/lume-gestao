import json
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.contrib import messages
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView, View

from accounts.permissions import ManagementAccessMixin
from billing.models import ServicePlan
from core.views import FormContextMixin, SearchableListView
from core.models import ClinicSettings
from website.content import INSTAGRAM_HIGHLIGHTS, REEL_FEATURES
from website.brevo import sync_newsletter_contact
from website.forms import WebsiteFAQForm, WebsiteNewsletterForm, WebsiteSettingsForm, WebsiteTestimonialForm
from website.models import (
    WebsiteFAQ,
    WebsiteGalleryItem,
    WebsiteNewsletterSubscriber,
    WebsiteService,
    WebsiteSettings,
    WebsiteTestimonial,
)


class WebsitePublicContextMixin:
    landing_hero_title = "Cuidado presencial para voltar a se mover com segurança."
    landing_hero_subtitle = (
        "A Lume combina fisioterapia, Pilates e terapias corporais em uma rotina orientada, "
        "com escuta próxima desde o primeiro contato."
    )
    service_cards = [
        {
            "title": "Pilates",
            "description": "Aulas orientadas para força, postura, mobilidade e consciência corporal, com atenção ao limite de cada aluno.",
        },
        {
            "title": "Fisioterapia",
            "description": "Avaliação e acompanhamento para dor, lesões, limitações funcionais, recuperação e prevenção.",
        },
        {
            "title": "Massagem",
            "description": "Cuidado corporal para aliviar tensões, desacelerar e recuperar conforto na rotina.",
        },
        {
            "title": "Reiki",
            "description": "Terapia complementar para pausa, relaxamento e equilíbrio, sempre respeitando seu momento.",
        },
    ]
    journey_steps = [
        "Você conta sua necessidade e a equipe entende o que está acontecendo.",
        "A Lume orienta o atendimento, frequência ou combinação mais adequada.",
        "Você agenda o primeiro passo e inicia o acompanhamento com clareza.",
    ]
    quick_benefits = [
        "Avaliação antes da indicação",
        "Atendimento presencial em Penedo/AL",
        "Continuidade com Lume em casa",
    ]
    trust_points = [
        {
            "label": "Primeiro passo",
            "title": "Você não precisa escolher sozinho",
            "text": "A equipe escuta sua necessidade antes de indicar atendimento, frequência ou plano.",
        },
        {
            "label": "Rotina real",
            "title": "Cuidado que cabe na semana",
            "text": "A orientação considera disponibilidade, evolução e continuidade fora do estúdio.",
        },
        {
            "label": "Presença local",
            "title": "Estúdio em Penedo, acompanhamento próximo",
            "text": "Endereço, horários e contato ficam claros para reduzir dúvida antes da visita.",
        },
    ]
    default_faqs = [
        {
            "question": "Quais atendimentos vocês oferecem?",
            "answer": "A Lume apresenta Pilates, fisioterapia, massagem e Reiki. Pelo WhatsApp, a equipe orienta qual caminho combina melhor com sua necessidade.",
        },
        {
            "question": "Como faço para agendar?",
            "answer": "O agendamento começa pelo WhatsApp. Você conta o que procura e a equipe combina o melhor horário disponível.",
        },
        {
            "question": "Como funcionam os planos?",
            "answer": "Os planos variam pela frequência semanal. Confirme disponibilidade, valores e melhor opção diretamente com a equipe.",
        },
        {
            "question": "Onde fica o studio?",
            "answer": "O studio fica em Penedo/AL, no endereço exibido nesta página.",
        },
        {
            "question": "Vocês atendem pelo WhatsApp?",
            "answer": "Sim. O WhatsApp é o principal caminho para tirar dúvidas e iniciar o agendamento.",
        },
    ]
    whatsapp_messages = {
        "general": "Olá, equipe Lume. Quero agendar uma avaliação.",
        "services": "Olá, equipe Lume. Não sei qual atendimento escolher e gostaria de orientação.",
        "homecare": "Olá, equipe Lume. Quero conhecer o Lume em casa.",
        "contact": "Olá, equipe Lume. Quero falar com a equipe e receber orientação.",
    }

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
            def faq_value(faq, key):
                return faq[key] if isinstance(faq, dict) else getattr(faq, key)

            graph.append(
                {
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": faq_value(faq, "question"),
                            "acceptedAnswer": {"@type": "Answer", "text": faq_value(faq, "answer")},
                        }
                        for faq in faqs
                    ],
                }
            )
        return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)

    def whatsapp_redirect_url(self, message_key="general", message=None):
        message_text = message or self.whatsapp_messages.get(message_key, self.whatsapp_messages["general"])
        return f"{reverse('website_whatsapp_redirect')}?{urlencode({'message': message_text})}"


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
        featured_plan = next((plan for plan in plans if plan.highlight_badge), None)
        faqs = list(WebsiteFAQ.objects.filter(active=True)[:6])
        public_faqs = faqs or self.default_faqs
        testimonials = list(WebsiteTestimonial.objects.filter(active=True)[:3])
        configured_services = list(WebsiteService.objects.filter(active=True)[:6])
        gallery_items = list(WebsiteGalleryItem.objects.filter(active=True)[:8])
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
                "landing_hero_title": self.landing_hero_title,
                "landing_hero_subtitle": self.landing_hero_subtitle,
                "service_cards": configured_services or self.service_cards,
                "journey_steps": self.journey_steps,
                "quick_benefits": self.quick_benefits,
                "trust_points": self.trust_points,
                "faqs": public_faqs,
                "testimonials": testimonials,
                "gallery_items": gallery_items,
                "newsletter_form": WebsiteNewsletterForm(),
                "assistant_questions": assistant_questions,
                "assistant_faq_map_json": assistant_answers,
                "reel_features": REEL_FEATURES,
                "instagram_highlights": INSTAGRAM_HIGHLIGHTS,
                "whatsapp_general_url": self.whatsapp_redirect_url("general"),
                "whatsapp_services_url": self.whatsapp_redirect_url("services"),
                "whatsapp_homecare_url": self.whatsapp_redirect_url("homecare"),
                "whatsapp_contact_url": self.whatsapp_redirect_url("contact"),
                "structured_data_json": self.build_structured_data(website_settings, public_faqs),
                "current_year": date.today().year,
            }
        )
        for plan in plans:
            plan.landing_featured = plan == featured_plan
            sessions_text = "1 sessão por semana" if plan.sessions_per_week == 1 else f"{plan.sessions_per_week} sessões por semana"
            plan.whatsapp_sessions_text = sessions_text
            plan.whatsapp_url = self.whatsapp_redirect_url(
                message=f"Olá, equipe Lume. Tenho interesse no plano {plan.name} ({sessions_text})."
            )
        return context


class WebsiteNewsletterSubscribeView(View):
    def post(self, request):
        form = WebsiteNewsletterForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Informe um e-mail valido e confirme o consentimento.")
            return redirect(f"{reverse('website_home')}#newsletter")

        website_settings = WebsiteSettings.load()
        subscriber, _ = WebsiteNewsletterSubscriber.objects.update_or_create(
            email=form.cleaned_data["email"].strip().lower(),
            defaults={
                "active": True,
                "consented_at": timezone.now(),
                "source": "landing",
            },
        )
        synced, error = sync_newsletter_contact(
            subscriber.email,
            website_settings.brevo_marketing_list_id,
        )
        subscriber.brevo_contact_synced = synced
        subscriber.brevo_error = error
        subscriber.save(update_fields=["brevo_contact_synced", "brevo_error", "updated_at"])
        messages.success(
            request,
            "Cadastro realizado. Voce recebera apenas novidades da Lume e podera sair quando quiser.",
        )
        return redirect(f"{reverse('website_home')}#newsletter")


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
        target_url = website_settings.resolved_whatsapp_url
        message = (self.request.GET.get("message") or "").strip()
        if self.counter_field == "whatsapp_clicks" and message:
            parsed_url = urlparse(target_url)
            query_items = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
            query_items["text"] = message
            target_url = urlunparse(parsed_url._replace(query=urlencode(query_items)))
        return target_url

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
