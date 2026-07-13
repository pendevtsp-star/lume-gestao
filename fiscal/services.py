from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from core.exports import br_currency, pdf_response
from core.integrations.whatsapp import send_whatsapp_text
from core.models import ClinicSettings


def build_document_pdf(document):
    clinic = ClinicSettings.load()
    disclaimer = "Documento fiscal registrado no Lume. Valide a autorizacao oficial com prefeitura/provedor."
    if document.document_type == document.DocumentType.RECEIPT:
        disclaimer = "Comprovante interno: nao substitui NFS-e quando houver exigencia fiscal municipal."

    sections = [
        (
            "Identificacao",
            [
                f"Clinica: {clinic.clinic_name}",
                f"CNPJ: {clinic.cnpj or '-'}",
                f"Endereco: {clinic.address or '-'}",
            ],
        ),
        (
            "Documento",
            [
                f"Tipo: {document.get_document_type_display()}",
                f"Status: {document.get_status_display()}",
                f"Data: {document.issue_date:%d/%m/%Y}",
                f"Referencia: {document.external_id or '-'}",
                f"Codigo de verificacao: {document.verification_code or '-'}",
            ],
        ),
        (
            "Servico",
            [
                f"Descricao: {document.description or '-'}",
                f"Codigo do servico: {document.service_code or '-'}",
                disclaimer,
                f"Gerado em {timezone.localtime():%d/%m/%Y %H:%M}",
            ],
        ),
    ]
    tables = [
        (
            "Tomador",
            ["Nome", "CPF/CNPJ", "E-mail", "WhatsApp"],
            [
                (
                    document.customer_name,
                    document.customer_document or "-",
                    document.customer_email or "-",
                    document.customer_phone or "-",
                )
            ],
        ),
        (
            "Valores",
            ["Valor do servico", "ISS", "Valor ISS", "Total"],
            [
                (
                    br_currency(document.amount),
                    f"{document.iss_rate:.2f}%".replace(".", ","),
                    br_currency(document.iss_amount),
                    br_currency(document.total_amount),
                )
            ],
        ),
    ]
    response = pdf_response(
        "documento-fiscal-lume.pdf",
        f"{document.get_document_type_display()} - Lume",
        sections=sections,
        tables=tables,
    )
    return response.content


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
        from_email=settings.EMAIL_TRANSACTIONAL_FROM_EMAIL,
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
