from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import UserProfile
from billing.models import ServicePlan
from website.models import WebsiteFAQ, WebsiteSettings, WebsiteTestimonial


@override_settings(
    ALLOWED_HOSTS=["testserver", "clinicafisiolume.com.br", "www.clinicafisiolume.com.br", "sistema.clinicafisiolume.com.br"],
    WEBSITE_HOSTS=["clinicafisiolume.com.br", "www.clinicafisiolume.com.br"],
    WEBSITE_BASE_URL="https://clinicafisiolume.com.br",
    SYSTEM_BASE_URL="https://sistema.clinicafisiolume.com.br",
)
class WebsitePublicTests(TestCase):
    def setUp(self):
        WebsiteFAQ.objects.create(
            question="Como faco para agendar?",
            answer="Fale com a equipe pelo WhatsApp para encontrar o atendimento ideal e combinar o melhor horario.",
            display_order=1,
        )
        WebsiteTestimonial.objects.create(
            author_name="Mariana",
            author_role="Paciente de Pilates",
            body="Atendimento humano e atencioso.",
            display_order=1,
        )
        ServicePlan.objects.create(
            name="Plano Pilates Essencial",
            category=ServicePlan.Category.PILATES,
            monthly_price=Decimal("320.00"),
            sessions_per_week=2,
            description="Descricao interna",
            public_description="Descricao publica do plano de Pilates.",
            show_on_website=True,
            display_order=2,
            highlight_badge="Mais procurado",
        )
        ServicePlan.objects.create(
            name="Plano Oculto",
            category=ServicePlan.Category.PHYSIOTHERAPY,
            monthly_price=Decimal("410.00"),
            sessions_per_week=1,
            show_on_website=False,
        )

    def test_public_host_serves_marketing_site(self):
        response = self.client.get("/", HTTP_HOST="clinicafisiolume.com.br")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cuidado presencial para voltar a se mover")
        self.assertContains(response, "Agendar")
        self.assertContains(response, "Plano Pilates Essencial")
        self.assertNotContains(response, "Plano Oculto")

    def test_system_host_keeps_backoffice_behavior(self):
        response = self.client.get("/", HTTP_HOST="sistema.clinicafisiolume.com.br")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_tracked_redirects_increment_click_counters(self):
        response = self.client.get("/ir/whatsapp/", HTTP_HOST="clinicafisiolume.com.br")
        website_settings = WebsiteSettings.load()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], website_settings.resolved_whatsapp_url)
        self.assertEqual(website_settings.whatsapp_clicks, 1)

        response = self.client.get(
            "/ir/whatsapp/?message=Quero%20este%20plano",
            HTTP_HOST="clinicafisiolume.com.br",
        )
        website_settings.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertIn("text=Quero+este+plano", response["Location"])
        self.assertEqual(website_settings.whatsapp_clicks, 2)

        response = self.client.get("/ir/sistema/", HTTP_HOST="clinicafisiolume.com.br")
        website_settings.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], website_settings.resolved_system_url)
        self.assertEqual(website_settings.system_clicks, 1)

    def test_instagram_redirect_uses_configured_url(self):
        response = self.client.get("/ir/instagram/", HTTP_HOST="clinicafisiolume.com.br")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], WebsiteSettings.load().resolved_instagram_url)

    def test_robots_and_sitemap_are_public(self):
        robots = self.client.get("/robots.txt", HTTP_HOST="clinicafisiolume.com.br")
        sitemap = self.client.get("/sitemap.xml", HTTP_HOST="clinicafisiolume.com.br")

        self.assertContains(robots, "Sitemap: https://clinicafisiolume.com.br/sitemap.xml")
        self.assertContains(sitemap, "<loc>https://clinicafisiolume.com.br/</loc>")


@override_settings(
    ALLOWED_HOSTS=["testserver", "clinicafisiolume.com.br", "sistema.clinicafisiolume.com.br"],
    WEBSITE_HOSTS=["clinicafisiolume.com.br"],
    WEBSITE_BASE_URL="https://clinicafisiolume.com.br",
    SYSTEM_BASE_URL="https://sistema.clinicafisiolume.com.br",
)
class WebsiteManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="gestor-site", password="Senha@123")
        UserProfile.objects.update_or_create(user=self.user, defaults={"role": UserProfile.Role.MANAGEMENT})
        self.client.force_login(self.user)

    def test_management_can_update_site_settings(self):
        response = self.client.post(
            reverse("website:settings"),
            {
                "clinic_name": "Lume Studio Fisio",
                "hero_title": "Seu corpo em movimento com apoio especializado.",
                "hero_subtitle": "Texto comercial do site.",
                "institutional_title": "Sobre a Lume",
                "institutional_text": "Texto institucional editavel.",
                "primary_cta_text": "Agendar agora",
                "system_cta_text": "Entrar no sistema",
                "whatsapp_url": "https://wa.me/message/GTYUJB6MIJJUJ1",
                "system_url": "https://sistema.clinicafisiolume.com.br",
                "instagram_url": "https://www.instagram.com/lumestudiofisio/",
                "address_line": "Av. Sao Luiz, 245",
                "city_name": "Penedo, AL",
                "business_hours": "Segunda a sexta, das 8h as 18h",
                "seo_title": "SEO title ajustado",
                "seo_description": "Descricao SEO ajustada.",
                "assistant_enabled": "on",
            },
            HTTP_HOST="sistema.clinicafisiolume.com.br",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(WebsiteSettings.load().seo_title, "SEO title ajustado")

    def test_management_can_crud_faqs_and_testimonials(self):
        faq_response = self.client.post(
            reverse("website:faq_create"),
            {
                "question": "Aceita atendimento individual?",
                "answer": "Sim, o atendimento e definido conforme a necessidade.",
                "display_order": 1,
                "active": "on",
            },
            HTTP_HOST="sistema.clinicafisiolume.com.br",
        )
        testimonial_response = self.client.post(
            reverse("website:testimonial_create"),
            {
                "author_name": "Ana",
                "author_role": "Paciente",
                "body": "Gostei muito do acompanhamento.",
                "display_order": 1,
                "active": "on",
            },
            HTTP_HOST="sistema.clinicafisiolume.com.br",
        )

        self.assertEqual(faq_response.status_code, 302)
        self.assertEqual(testimonial_response.status_code, 302)
        self.assertEqual(WebsiteFAQ.objects.count(), 1)
        self.assertEqual(WebsiteTestimonial.objects.count(), 1)
