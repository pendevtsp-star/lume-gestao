from django.conf import settings
from django.db import models

from core.models import ClinicSettings, TimeStampedModel


DEFAULT_WHATSAPP_URL = "https://wa.me/message/GTYUJB6MIJJUJ1"
DEFAULT_INSTAGRAM_URL = "https://www.instagram.com/lumestudiofisio/"


class WebsiteSettings(TimeStampedModel):
    clinic_name = models.CharField("nome exibido", max_length=140, default="Lume Studio Fisio")
    hero_title = models.CharField(
        "titulo principal",
        max_length=180,
        default="Movimento consciente para reabilitar, prevenir e viver melhor.",
    )
    hero_subtitle = models.TextField(
        "subtitulo principal",
        default=(
            "Pilates, fisioterapia, massagem e Reiki em um atendimento acolhedor, humano e pensado para a sua rotina."
        ),
    )
    institutional_title = models.CharField("titulo institucional", max_length=140, default="Cuidado que acompanha cada fase")
    institutional_text = models.TextField(
        "texto institucional",
        default=(
            "A Lume une tecnica, escuta e acompanhamento proximo para ajudar cada paciente a recuperar funcao, "
            "ganhar autonomia e manter o corpo em movimento com seguranca."
        ),
    )
    primary_cta_text = models.CharField("texto do CTA principal", max_length=60, default="Agendar pelo WhatsApp")
    system_cta_text = models.CharField("texto do CTA do sistema", max_length=60, default="Acessar sistema")
    whatsapp_url = models.URLField("link do WhatsApp", default=DEFAULT_WHATSAPP_URL)
    system_url = models.URLField(
        "link do sistema",
        default="https://sistema.clinicafisiolume.com.br",
        help_text="URL publica do sistema operacional da clinica.",
    )
    instagram_url = models.URLField("link do Instagram", default=DEFAULT_INSTAGRAM_URL)
    address_line = models.CharField("endereco exibido", max_length=255, blank=True, default="Av. Sao Luiz, 245")
    city_name = models.CharField("cidade/regiao", max_length=120, default="Penedo, AL")
    business_hours = models.CharField("horario exibido", max_length=120, blank=True, default="Segunda a sexta, das 8h as 18h")
    seo_title = models.CharField(
        "SEO title",
        max_length=160,
        default="Lume Studio Fisio | Pilates, Fisioterapia e Bem-estar em Penedo/AL",
    )
    seo_description = models.CharField(
        "SEO description",
        max_length=255,
        default=(
            "Conheca a Lume Studio Fisio em Penedo/AL para Pilates, fisioterapia, massagem e Reiki com atendimento "
            "acolhedor e agendamento rapido pelo WhatsApp."
        ),
    )
    assistant_enabled = models.BooleanField("assistente virtual ativo", default=True)
    whatsapp_clicks = models.PositiveIntegerField("cliques no WhatsApp", default=0)
    system_clicks = models.PositiveIntegerField("cliques no sistema", default=0)

    class Meta:
        verbose_name = "configuracao do site"
        verbose_name_plural = "configuracoes do site"

    def __str__(self):
        return self.clinic_name

    @property
    def resolved_clinic_name(self):
        clinic_name = self.clinic_name.strip()
        if clinic_name:
            return clinic_name
        return ClinicSettings.load().clinic_name

    @property
    def resolved_address(self):
        if self.address_line.strip():
            return self.address_line
        return ClinicSettings.load().address

    @property
    def resolved_business_hours(self):
        if self.business_hours.strip():
            return self.business_hours
        clinic = ClinicSettings.load()
        return f"{clinic.business_days}, das {clinic.opening_time:%H:%M} as {clinic.closing_time:%H:%M}"

    @property
    def resolved_system_url(self):
        return self.system_url or settings.SYSTEM_BASE_URL or "https://sistema.clinicafisiolume.com.br"

    @property
    def resolved_whatsapp_url(self):
        return self.whatsapp_url or DEFAULT_WHATSAPP_URL

    @property
    def resolved_instagram_url(self):
        return self.instagram_url or DEFAULT_INSTAGRAM_URL

    @classmethod
    def load(cls):
        settings_object, _ = cls.objects.get_or_create(pk=1)
        return settings_object


class WebsiteFAQ(TimeStampedModel):
    question = models.CharField("pergunta", max_length=180)
    answer = models.TextField("resposta")
    display_order = models.PositiveSmallIntegerField("ordem", default=0)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["display_order", "question"]
        verbose_name = "FAQ do site"
        verbose_name_plural = "FAQs do site"

    def __str__(self):
        return self.question


class WebsiteTestimonial(TimeStampedModel):
    author_name = models.CharField("nome", max_length=120)
    author_role = models.CharField("identificacao", max_length=140, blank=True)
    body = models.TextField("depoimento")
    display_order = models.PositiveSmallIntegerField("ordem", default=0)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["display_order", "author_name"]
        verbose_name = "depoimento do site"
        verbose_name_plural = "depoimentos do site"

    def __str__(self):
        return self.author_name
