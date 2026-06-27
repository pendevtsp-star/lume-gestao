from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from fiscal.models import FiscalDocument
from patients.models import Patient


class FiscalModuleTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="gestor", password="senha123")
        profile, _created = UserProfile.objects.get_or_create(user=user)
        profile.role = UserProfile.Role.MANAGEMENT
        profile.save(update_fields=["role"])
        self.client.force_login(user)
        self.patient = Patient.objects.create(
            full_name="Maria Clara",
            cpf="12345678901",
            email="maria@example.com",
            phone="11999990000",
        )

    def test_dashboard_loads_for_management(self):
        response = self.client.get(reverse("fiscal:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NFS-e, recibos internos")

    def test_create_and_issue_fiscal_document(self):
        response = self.client.post(
            reverse("fiscal:document_create"),
            {
                "document_type": FiscalDocument.DocumentType.NFSE,
                "patient": self.patient.pk,
                "issue_date": "2026-06-27",
                "description": "Sessao de fisioterapia",
                "amount": "180.00",
                "iss_rate": "2.00",
                "customer_name": "Maria Clara",
                "customer_document": "12345678901",
                "customer_email": "maria@example.com",
                "customer_phone": "11999990000",
            },
        )
        self.assertRedirects(response, reverse("fiscal:dashboard"))
        document = FiscalDocument.objects.get()
        self.assertEqual(document.iss_amount, Decimal("3.60"))

        response = self.client.post(reverse("fiscal:document_issue", args=[document.pk]))
        self.assertRedirects(response, reverse("fiscal:dashboard"))
        document.refresh_from_db()
        self.assertEqual(document.status, FiscalDocument.Status.ISSUED)
        self.assertTrue(document.external_id.startswith("LUME-NFSE"))

    def test_pdf_export_returns_pdf(self):
        document = FiscalDocument.objects.create(
            document_type=FiscalDocument.DocumentType.RECEIPT,
            patient=self.patient,
            description="Aula de pilates",
            amount=Decimal("120.00"),
            iss_rate=Decimal("0.00"),
            customer_name="Maria Clara",
        )
        response = self.client.get(reverse("fiscal:document_pdf", args=[document.pk]))
        inline_response = self.client.get(reverse("fiscal:document_pdf", args=[document.pk]), {"inline": "1"})
        preview_response = self.client.get(reverse("fiscal:document_pdf_preview", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(inline_response["Content-Type"], "application/pdf")
        self.assertIn("inline", inline_response["Content-Disposition"])
        self.assertContains(preview_response, "Pre-visualizar documento fiscal")
        self.assertContains(preview_response, "Baixar PDF")
