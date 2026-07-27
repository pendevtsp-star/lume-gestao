from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from core.forms import ClinicSettingsForm
from core.validators import validate_image_upload


class ImageUploadSecurityTests(SimpleTestCase):
    @override_settings(LUME_MAX_IMAGE_UPLOAD_MB=1)
    def test_rejects_image_larger_than_configured_limit(self):
        upload = SimpleUploadedFile(
            "large.jpg",
            b"x" * (1024 * 1024 + 1),
            content_type="image/jpeg",
        )

        with self.assertRaisesMessage(forms.ValidationError, "1 MB"):
            validate_image_upload(upload)

    def test_rejects_disallowed_extension(self):
        upload = SimpleUploadedFile(
            "payload.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            content_type="image/svg+xml",
        )

        with self.assertRaisesMessage(forms.ValidationError, "JPG, PNG ou WebP"):
            validate_image_upload(upload)

    def test_rejects_disallowed_content_type(self):
        upload = SimpleUploadedFile(
            "payload.jpg",
            b"not-an-image",
            content_type="text/html",
        )

        with self.assertRaisesMessage(forms.ValidationError, "tipo de arquivo"):
            validate_image_upload(upload)

    def test_clinic_logo_uses_the_image_upload_validator(self):
        upload = SimpleUploadedFile(
            "logo.pdf",
            b"%PDF-1.4",
            content_type="application/pdf",
        )

        form = ClinicSettingsForm(data={}, files={"logo": upload})

        self.assertFalse(form.is_valid())
        self.assertIn("Envie uma imagem JPG, PNG ou WebP.", form.errors["logo"])
