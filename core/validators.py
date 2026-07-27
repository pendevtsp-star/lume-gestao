from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_image_upload(upload):
    """Reject unexpectedly large or non-raster image uploads before storage."""
    if not upload:
        return upload

    max_mb = int(getattr(settings, "LUME_MAX_IMAGE_UPLOAD_MB", 5))
    if upload.size > max_mb * 1024 * 1024:
        raise ValidationError(f"A imagem deve ter no maximo {max_mb} MB.")

    extension = Path(upload.name or "").suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError("Envie uma imagem JPG, PNG ou WebP.")

    content_type = (getattr(upload, "content_type", "") or "").lower()
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValidationError("O tipo de arquivo enviado nao e permitido.")
    return upload
