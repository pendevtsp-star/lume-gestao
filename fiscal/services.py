from io import BytesIO

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from core.integrations.whatsapp import send_whatsapp_text
from core.models import ClinicSettings


def build_document_pdf(document):
    clinic = ClinicSettings.load()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 72
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(56, y, "Lume Gestao - Documento Fiscal")
    y -= 28
    pdf.setFont("Helvetica", 10)
    pdf.drawString(56, y, f"Clinica: {clinic.clinic_name}")
    y -= 16
    pdf.drawString(56, y, f"CNPJ: {clinic.cnpj or '-'}")
    y -= 16
    pdf.drawString(56, y, f"Endereco: {clinic.address or '-'}")
    y -= 28

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(56, y, document.get_document_type_display())
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(width - 56, y, f"Status: {document.get_status_display()}")
    y -= 22
    pdf.drawString(56, y, f"Data: {document.issue_date:%d/%m/%Y}")
    pdf.drawRightString(width - 56, y, f"Referencia: {document.external_id or '-'}")
    y -= 16
    pdf.drawString(56, y, f"Codigo de verificacao: {document.verification_code or '-'}")
    y -= 30

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(56, y, "Tomador")
    y -= 18
    pdf.setFont("Helvetica", 10)
    pdf.drawString(56, y, f"Nome: {document.customer_name}")
    y -= 16
    pdf.drawString(56, y, f"CPF/CNPJ: {document.customer_document or '-'}")
    y -= 16
    pdf.drawString(56, y, f"E-mail: {document.customer_email or '-'}")
    y -= 16
    pdf.drawString(56, y, f"WhatsApp: {document.customer_phone or '-'}")
    y -= 30

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(56, y, "Servico")
    y -= 18
    pdf.setFont("Helvetica", 10)
    text = pdf.beginText(56, y)
    text.setFont("Helvetica", 10)
    for line in _wrap_text(document.description, 82):
        text.textLine(line)
    pdf.drawText(text)
    y -= 18 * max(1, len(_wrap_text(document.description, 82)))
    pdf.drawString(56, y, f"Codigo do servico: {document.service_code or '-'}")
    y -= 30

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(56, y, "Valores")
    y -= 18
    pdf.setFont("Helvetica", 10)
    pdf.drawString(56, y, f"Valor do servico: R$ {document.amount:.2f}")
    y -= 16
    pdf.drawString(56, y, f"ISS ({document.iss_rate:.2f}%): R$ {document.iss_amount:.2f}")
    y -= 16
    pdf.drawString(56, y, f"Total: R$ {document.total_amount:.2f}")
    y -= 32

    pdf.setFont("Helvetica-Oblique", 9)
    if document.document_type == document.DocumentType.RECEIPT:
        pdf.drawString(56, y, "Comprovante interno: nao substitui NFS-e quando houver exigencia fiscal municipal.")
    else:
        pdf.drawString(56, y, "Documento fiscal registrado no Lume. Valide a autorizacao oficial com prefeitura/provedor.")
    y -= 16
    pdf.drawString(56, y, f"Gerado em {timezone.localtime():%d/%m/%Y %H:%M}")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def send_document_email(document):
    if not document.customer_email:
        raise ValueError("O tomador nao possui e-mail cadastrado.")
    pdf_content = build_document_pdf(document)
    message = EmailMessage(
        subject=f"{document.get_document_type_display()} - Lume Gestao",
        body=(
            f"Ola, {document.customer_name}.\n\n"
            f"Segue em anexo o documento referente a {document.description}.\n\n"
            "Equipe Lume Gestao"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[document.customer_email],
    )
    message.attach(f"documento-fiscal-{document.pk}.pdf", pdf_content, "application/pdf")
    return message.send()


def send_document_whatsapp(document):
    if not document.customer_phone:
        raise ValueError("O tomador nao possui WhatsApp cadastrado.")
    message = (
        f"Ola, {document.customer_name}! Seu {document.get_document_type_display()} "
        f"referente a {document.description} no valor de R$ {document.total_amount:.2f} "
        "foi gerado no Lume Gestao. Solicite o PDF caso precise do arquivo."
    )
    return send_whatsapp_text(document.customer_phone, message)


def _wrap_text(value, width):
    words = str(value or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ["-"]
