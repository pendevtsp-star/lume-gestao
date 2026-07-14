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
        default="Cuidado presencial para voltar a se mover com seguranca.",
    )
    hero_subtitle = models.TextField(
        "subtitulo principal",
        default=(
            "A Lume combina fisioterapia, Pilates e terapias corporais em uma rotina orientada, "
            "com escuta proxima desde o primeiro contato."
        ),
    )
    hero_eyebrow = models.CharField(
        "chamada acima do titulo",
        max_length=120,
        default="Pilates e fisioterapia em Penedo, AL",
    )
    services_title = models.CharField(
        "titulo dos atendimentos",
        max_length=180,
        default="Atendimentos para cuidar do corpo com clareza e acolhimento.",
    )
    services_text = models.TextField(
        "texto dos atendimentos",
        default=(
            "Voce pode chegar com dor, busca por movimento, tensao acumulada ou vontade de manter uma rotina "
            "mais saudavel. A equipe ajuda a traduzir isso em um caminho de cuidado."
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
    gallery_title = models.CharField(
        "titulo da galeria",
        max_length=180,
        default="Um pouco do cuidado que acontece na Lume.",
    )
    gallery_text = models.TextField(
        "texto da galeria",
        default="Registros do estudio ajudam voce a sentir o ambiente antes de marcar a primeira visita.",
    )
    testimonials_title = models.CharField(
        "titulo dos depoimentos",
        max_length=180,
        default="O que nossos pacientes sentem.",
    )
    homecare_title = models.CharField(
        "titulo do Lume em casa",
        max_length=180,
        default="Lume em casa entra depois da orientacao presencial.",
    )
    homecare_text = models.TextField(
        "texto do Lume em casa",
        default=(
            "A biblioteca de aulas gravadas apoia a rotina do paciente entre os atendimentos, "
            "com conteudos organizados por foco, nivel e duracao."
        ),
    )
    homecare_video_url = models.URLField("video do Lume em casa", blank=True)
    plans_title = models.CharField(
        "titulo dos planos",
        max_length=180,
        default="Planos para manter sua rotina de cuidado.",
    )
    plans_text = models.TextField(
        "texto dos planos",
        default=(
            "Os planos ajudam a manter frequencia. Se voce ainda nao sabe qual escolher, "
            "fale com a equipe antes de decidir."
        ),
    )
    faq_title = models.CharField("titulo das duvidas", max_length=160, default="Informacoes essenciais.")
    contact_title = models.CharField(
        "titulo do contato",
        max_length=180,
        default="Conte seu caso. A Lume orienta o primeiro passo.",
    )
    contact_text = models.TextField(
        "texto do contato",
        default=(
            "Diga o que voce sente, o que procura ou qual rotina deseja construir. "
            "A equipe responde pelo WhatsApp e indica o caminho mais adequado."
        ),
    )
    footer_text = models.TextField(
        "texto do rodape",
        default="Cuidado presencial e continuidade para uma rotina com mais movimento e seguranca.",
    )
    newsletter_title = models.CharField(
        "titulo da lista de e-mail",
        max_length=140,
        default="Receba novidades da Lume",
    )
    newsletter_text = models.CharField(
        "texto da lista de e-mail",
        max_length=255,
        default="Conteudos de cuidado, agenda e novidades do studio.",
    )
    brevo_marketing_list_id = models.PositiveIntegerField(
        "ID da lista Brevo",
        null=True,
        blank=True,
        help_text="Lista de contatos que recebera as inscricoes realizadas pela landing page.",
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


class WebsiteService(TimeStampedModel):
    title = models.CharField("titulo", max_length=120)
    description = models.TextField("descricao")
    icon = models.CharField(
        "icone",
        max_length=40,
        blank=True,
        help_text="Nome de um icone Material Symbols, como accessibility_new ou spa.",
    )
    display_order = models.PositiveSmallIntegerField("ordem", default=0)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["display_order", "title"]
        verbose_name = "atendimento do site"
        verbose_name_plural = "atendimentos do site"

    def __str__(self):
        return self.title


class WebsiteGalleryItem(TimeStampedModel):
    title = models.CharField("titulo", max_length=140)
    image = models.ImageField("imagem", upload_to="website/gallery/")
    alt_text = models.CharField("texto alternativo", max_length=180)
    external_url = models.URLField("link externo", blank=True)
    display_order = models.PositiveSmallIntegerField("ordem", default=0)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["display_order", "title"]
        verbose_name = "imagem da galeria"
        verbose_name_plural = "imagens da galeria"

    def __str__(self):
        return self.title


class WebsiteNewsletterSubscriber(TimeStampedModel):
    email = models.EmailField("e-mail", unique=True)
    active = models.BooleanField("ativo", default=True)
    consented_at = models.DateTimeField("consentimento em")
    source = models.CharField("origem", max_length=60, default="landing")
    brevo_contact_synced = models.BooleanField("sincronizado com Brevo", default=False)
    brevo_error = models.TextField("erro da Brevo", blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "inscrito da landing"
        verbose_name_plural = "inscritos da landing"

    def __str__(self):
        return self.email
