from django import forms
from django.conf import settings

from accounts.models import UserProfile
from accounts.permissions import get_profile
from core.forms import StyledModelForm
from lume_connect.models import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS, ConnectComment, ConnectPost
from lume_connect.services.video_metadata import get_mp4_duration_seconds


class ConnectPostForm(StyledModelForm):
    class Meta:
        model = ConnectPost
        fields = ["content", "image", "video", "video_thumbnail", "is_pinned", "is_announcement"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Compartilhe uma novidade, foto, video curto ou recado com a comunidade.",
                }
            ),
            "video": forms.FileInput(attrs={"accept": ".mp4,.mov,video/mp4,video/quicktime"}),
            "video_thumbnail": forms.FileInput(attrs={"accept": ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self._video_duration_seconds = None
        self._video_size_bytes = None
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
        self.fields["video"].help_text = "MP4 ou MOV, ate %s MB e ate %s segundos." % (
            getattr(settings, "LUME_CONNECT_MAX_VIDEO_MB", 80),
            getattr(settings, "LUME_CONNECT_MAX_SHORT_VIDEO_SECONDS", 60),
        )
        self.fields["video_thumbnail"].help_text = "Opcional. JPG, PNG ou WEBP."
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

    def clean_video(self):
        video = self.cleaned_data.get("video")
        if not video:
            return video

        max_mb = getattr(settings, "LUME_CONNECT_MAX_VIDEO_MB", 80)
        if video.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(f"O video deve ter no maximo {max_mb} MB.")

        extension = video.name.rsplit(".", 1)[-1].lower() if "." in video.name else ""
        if extension not in ALLOWED_VIDEO_EXTENSIONS:
            raise forms.ValidationError("Use um video MP4 ou MOV.")

        content_type = getattr(video, "content_type", "")
        allowed_content_types = {"video/mp4", "video/quicktime", "application/mp4", "application/octet-stream"}
        if content_type and content_type not in allowed_content_types:
            raise forms.ValidationError("O arquivo enviado nao parece ser um video MP4 ou MOV permitido.")

        duration = get_mp4_duration_seconds(video)
        max_seconds = getattr(settings, "LUME_CONNECT_MAX_SHORT_VIDEO_SECONDS", 60)
        if duration is None:
            raise forms.ValidationError("Nao foi possivel confirmar a duracao do video. Envie um MP4 ou MOV valido.")
        if duration > max_seconds:
            raise forms.ValidationError(f"Videos curtos devem ter no maximo {max_seconds} segundos.")
        self._video_duration_seconds = duration
        self._video_size_bytes = video.size
        return video

    def clean_video_thumbnail(self):
        thumbnail = self.cleaned_data.get("video_thumbnail")
        if not thumbnail:
            return thumbnail
        max_mb = getattr(settings, "LUME_CONNECT_MAX_IMAGE_MB", 8)
        if thumbnail.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(f"A capa deve ter no maximo {max_mb} MB.")
        extension = thumbnail.name.rsplit(".", 1)[-1].lower() if "." in thumbnail.name else ""
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise forms.ValidationError("Use uma capa JPG, JPEG, PNG ou WEBP.")
        content_type = getattr(thumbnail, "content_type", "")
        allowed_content_types = {"image/jpeg", "image/png", "image/webp"}
        if content_type and content_type not in allowed_content_types:
            raise forms.ValidationError("A capa enviada nao parece ser uma imagem permitida.")
        return thumbnail

    def clean(self):
        cleaned_data = super().clean()
        content = (cleaned_data.get("content") or "").strip()
        image = cleaned_data.get("image")
        video = cleaned_data.get("video")
        has_existing_image = bool(getattr(self.instance, "image", None))
        has_existing_video = bool(getattr(self.instance, "video", None))
        if image and video:
            raise forms.ValidationError("Escolha imagem ou video, nao os dois no mesmo post.")
        if not content and not image and not video and not has_existing_image and not has_existing_video:
            raise forms.ValidationError("Escreva um texto, adicione uma imagem ou envie um video curto para publicar.")
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

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("video"):
            instance.video_duration_seconds = self._video_duration_seconds
            instance.video_size_bytes = self._video_size_bytes
            instance.is_short_video = True
        elif self.cleaned_data.get("image"):
            instance.video_duration_seconds = None
            instance.video_size_bytes = None
            instance.is_short_video = False
        if commit:
            instance.save()
            self.save_m2m()
        return instance


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
