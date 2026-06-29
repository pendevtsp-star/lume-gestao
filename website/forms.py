from django import forms

from core.forms import StyledModelForm
from website.models import WebsiteFAQ, WebsiteSettings, WebsiteTestimonial


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
            "hero_title",
            "hero_subtitle",
            "institutional_title",
            "institutional_text",
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
            "institutional_text": forms.Textarea(attrs={"rows": 5}),
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
