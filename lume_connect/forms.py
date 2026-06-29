from django import forms
from django.conf import settings

from accounts.models import UserProfile
from accounts.permissions import get_profile
from core.forms import StyledModelForm
from lume_connect.models import ALLOWED_IMAGE_EXTENSIONS, ConnectComment, ConnectPost


class ConnectPostForm(StyledModelForm):
    class Meta:
        model = ConnectPost
        fields = ["content", "image", "is_pinned", "is_announcement"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Compartilhe uma novidade, foto ou recado com a comunidade.",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        profile = get_profile(self.user) if self.user and self.user.is_authenticated else None
        can_moderate = bool(
            self.user
            and (
                self.user.is_superuser
                or (profile and profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT})
            )
        )
        self.fields["image"].help_text = "JPG, PNG ou WEBP. Tamanho maximo: %s MB." % getattr(
            settings,
            "LUME_CONNECT_MAX_IMAGE_MB",
            8,
        )
        if not can_moderate:
            self.fields["is_pinned"].widget = forms.HiddenInput()
            self.fields["is_announcement"].widget = forms.HiddenInput()
            self.fields["is_pinned"].required = False
            self.fields["is_announcement"].required = False

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image

        max_mb = getattr(settings, "LUME_CONNECT_MAX_IMAGE_MB", 8)
        if image.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(f"A imagem deve ter no maximo {max_mb} MB.")

        extension = image.name.rsplit(".", 1)[-1].lower() if "." in image.name else ""
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise forms.ValidationError("Use uma imagem JPG, JPEG, PNG ou WEBP.")

        content_type = getattr(image, "content_type", "")
        allowed_content_types = {"image/jpeg", "image/png", "image/webp"}
        if content_type and content_type not in allowed_content_types:
            raise forms.ValidationError("O arquivo enviado nao parece ser uma imagem permitida.")
        return image

    def clean(self):
        cleaned_data = super().clean()
        content = (cleaned_data.get("content") or "").strip()
        image = cleaned_data.get("image")
        if not content and not image and not getattr(self.instance, "image", None):
            raise forms.ValidationError("Escreva um texto ou adicione uma imagem para publicar.")
        profile = get_profile(self.user) if self.user and self.user.is_authenticated else None
        can_moderate = bool(
            self.user
            and (
                self.user.is_superuser
                or (profile and profile.role in {UserProfile.Role.ADMINISTRATION, UserProfile.Role.MANAGEMENT})
            )
        )
        if not can_moderate:
            cleaned_data["is_pinned"] = getattr(self.instance, "is_pinned", False)
            cleaned_data["is_announcement"] = getattr(self.instance, "is_announcement", False)
        return cleaned_data


class ConnectCommentForm(StyledModelForm):
    class Meta:
        model = ConnectComment
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 2, "placeholder": "Escreva um comentario..."}),
        }

    def clean_content(self):
        content = self.cleaned_data["content"].strip()
        if not content:
            raise forms.ValidationError("Escreva um comentario antes de enviar.")
        return content
