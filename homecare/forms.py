from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from accounts.permissions import get_profile
from core.forms import StyledModelForm
from homecare.models import (
    HomecareCategory,
    HomecarePlan,
    HomecareSubscription,
    HomecareUploadJob,
    HomecareVideo,
    HomecareVideoComment,
)
from team.models import Professional


class HomecareCategoryForm(StyledModelForm):
    class Meta:
        model = HomecareCategory
        fields = ["name", "slug", "description", "display_order", "active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class HomecarePlanForm(StyledModelForm):
    class Meta:
        model = HomecarePlan
        fields = [
            "name",
            "slug",
            "description",
            "monthly_price",
            "billing_cycle",
            "display_order",
            "active",
            "public_checkout_enabled",
            "provider_plan_reference",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class HomecareVideoForm(StyledModelForm):
    upload_file = forms.FileField(
        label="arquivo do video",
        required=False,
        help_text="MP4, MOV, M4V ou WEBM.",
    )

    class Meta:
        model = HomecareVideo
        fields = [
            "title",
            "slug",
            "description",
            "category",
            "author",
            "specialty",
            "difficulty",
            "duration_seconds",
            "thumbnail",
            "scheduled_publish_at",
            "is_published",
            "upload_file",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "scheduled_publish_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = HomecareCategory.objects.filter(active=True)
        self.fields["author"].queryset = Professional.objects.filter(active=True)
        self.fields["specialty"].choices = [("", "---------"), *Professional.Specialty.choices]
        self.fields["title"].help_text = "Nome que aparece na biblioteca do paciente."
        self.fields["slug"].help_text = "Pode ficar em branco para ser gerado automaticamente."
        self.fields["duration_seconds"].help_text = "Use segundos para permitir filtros por duracao."
        self.fields["thumbnail"].help_text = "Imagem opcional de capa para a biblioteca."
        self.fields["is_published"].label = "publicar na biblioteca"
        self.fields["scheduled_publish_at"].label = "lancamento programado"
        self.fields["scheduled_publish_at"].help_text = (
            "Opcional. Se preenchido, o video aparece para assinantes somente a partir desta data e horario."
        )
        self.fields["scheduled_publish_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["upload_file"].help_text = (
            f"MP4 recomendado. MOV, M4V ou WEBM tambem sao aceitos, ate {settings.HOMECARE_MAX_UPLOAD_MB} MB."
        )
        self.fields["upload_file"].widget.attrs.update(
            {
                "class": "field-control file-input",
                "accept": ".mp4,.mov,.m4v,.webm,video/mp4,video/quicktime,video/webm",
            }
        )
        self.fields["thumbnail"].widget.attrs.update({"class": "field-control file-input", "accept": "image/*"})
        profile = get_profile(self.user)
        if profile and profile.is_professional and profile.professional_id and not self.user.is_superuser:
            self.fields["author"].initial = profile.professional
            self.fields["author"].disabled = True

    def clean_upload_file(self):
        upload = self.cleaned_data.get("upload_file")
        if not upload:
            return upload
        max_bytes = settings.HOMECARE_MAX_UPLOAD_MB * 1024 * 1024
        if upload.size > max_bytes:
            raise ValidationError(f"Envie um arquivo de ate {settings.HOMECARE_MAX_UPLOAD_MB} MB.")
        allowed_extensions = (".mp4", ".mov", ".m4v", ".webm")
        name = upload.name.lower()
        if not name.endswith(allowed_extensions):
            raise ValidationError("Use um arquivo MP4, MOV, M4V ou WEBM.")
        return upload

    def clean(self):
        cleaned = super().clean()
        scheduled_publish_at = cleaned.get("scheduled_publish_at")
        if scheduled_publish_at:
            cleaned["is_published"] = True
        if (
            cleaned.get("is_published")
            and not scheduled_publish_at
            and self.instance.status != HomecareVideo.Status.READY
        ):
            self.add_error("is_published", "Publique apenas depois que o upload estiver pronto.")
        return cleaned

    def save(self, commit=True):
        video = super().save(commit=False)
        profile = get_profile(self.user)
        if profile and profile.is_professional and profile.professional_id and not self.user.is_superuser:
            video.author = profile.professional
        upload = self.cleaned_data.get("upload_file")
        scheduled_publish_at = self.cleaned_data.get("scheduled_publish_at")
        if scheduled_publish_at:
            video.is_published = True
        if upload:
            provider = settings.HOMECARE_VIDEO_PROVIDER
            if provider in {HomecareVideo.Provider.LOCAL, HomecareVideo.Provider.BUNNY}:
                video.provider = provider
            video.temporary_file = upload
            video.status = HomecareVideo.Status.QUEUED
            video.upload_error = ""
            if not scheduled_publish_at:
                video.is_published = False
        if commit:
            video.save()
            if upload:
                HomecareUploadJob.objects.create(video=video)
            self.save_m2m()
        return video


class HomecareSubscriptionForm(StyledModelForm):
    class Meta:
        model = HomecareSubscription
        fields = [
            "patient",
            "plan",
            "status",
            "source",
            "provider",
            "starts_at",
            "current_period_start",
            "current_period_end",
            "provider_customer_id",
            "provider_subscription_id",
            "provider_payment_id",
            "checkout_url",
            "notes",
        ]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "current_period_start": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "current_period_end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class HomecareVideoCommentForm(StyledModelForm):
    class Meta:
        model = HomecareVideoComment
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 3,
                    "maxlength": 1200,
                    "required": "required",
                    "placeholder": "Escreva sua pergunta, percepcao ou ajuste que gostaria de comentar.",
                }
            ),
        }

    def clean_content(self):
        content = self.cleaned_data["content"].strip()
        if not content:
            raise forms.ValidationError("Escreva um comentario antes de enviar.")
        return content
