from django import forms

from core.forms import StyledModelForm
from website.models import WebsiteFAQ, WebsiteSettings, WebsiteTestimonial


class WebsiteNewsletterForm(forms.Form):
    email = forms.EmailField(
        label="Seu melhor e-mail",
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "seuemail@exemplo.com",
                "aria-label": "Seu melhor e-mail",
            }
        ),
    )
    consent = forms.BooleanField(
        label="Aceito receber novidades e posso cancelar a qualquer momento.",
        required=True,
    )


class WebsiteSettingsForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["whatsapp_url"].help_text = "Define o destino do botao flutuante e dos CTAs de WhatsApp no site."
        self.fields["instagram_url"].help_text = "Define o destino do botao flutuante e dos links de Instagram no site."
        self.fields["system_url"].help_text = "Define o acesso ao sistema pelo botao publico do site."

    class Meta:
        model = WebsiteSettings
        fields = [
            "clinic_name",
            "hero_eyebrow",
            "hero_title",
            "hero_subtitle",
            "services_title",
            "services_text",
            "institutional_title",
            "institutional_text",
            "gallery_title",
            "gallery_text",
            "testimonials_title",
            "homecare_title",
            "homecare_text",
            "homecare_video_url",
            "plans_title",
            "plans_text",
            "faq_title",
            "contact_title",
            "contact_text",
            "footer_text",
            "newsletter_title",
            "newsletter_text",
            "brevo_marketing_list_id",
            "primary_cta_text",
            "system_cta_text",
            "whatsapp_url",
            "system_url",
            "instagram_url",
            "address_line",
            "city_name",
            "business_hours",
            "seo_title",
            "seo_description",
            "assistant_enabled",
        ]
        widgets = {
            "hero_subtitle": forms.Textarea(attrs={"rows": 3}),
            "services_text": forms.Textarea(attrs={"rows": 3}),
            "institutional_text": forms.Textarea(attrs={"rows": 5}),
            "gallery_text": forms.Textarea(attrs={"rows": 3}),
            "homecare_text": forms.Textarea(attrs={"rows": 4}),
            "plans_text": forms.Textarea(attrs={"rows": 3}),
            "contact_text": forms.Textarea(attrs={"rows": 4}),
            "footer_text": forms.Textarea(attrs={"rows": 3}),
            "seo_description": forms.Textarea(attrs={"rows": 3}),
        }


class WebsiteFAQForm(StyledModelForm):
    class Meta:
        model = WebsiteFAQ
        fields = ["question", "answer", "display_order", "active"]
        widgets = {"answer": forms.Textarea(attrs={"rows": 5})}


class WebsiteTestimonialForm(StyledModelForm):
    class Meta:
        model = WebsiteTestimonial
        fields = ["author_name", "author_role", "body", "display_order", "active"]
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}
