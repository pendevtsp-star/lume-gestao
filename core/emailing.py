from django.conf import settings
from django.core.mail import EmailMultiAlternatives


class MarketingConsentRequired(ValueError):
    """Raised when a promotional email is requested without recorded consent."""


def transactional_sender():
    return settings.EMAIL_TRANSACTIONAL_FROM_EMAIL


def marketing_sender():
    return settings.EMAIL_MARKETING_FROM_EMAIL


def send_transactional_email(*, subject, text_body, html_body, recipients, reply_to=None):
    """Send operational messages such as access recovery, billing and documents."""
    message = EmailMultiAlternatives(
        subject,
        text_body,
        transactional_sender(),
        recipients,
        reply_to=reply_to or ([settings.EMAIL_REPLY_TO] if settings.EMAIL_REPLY_TO else None),
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(fail_silently=False)


def send_marketing_email(*, patient, subject, text_body, html_body):
    """Marketing is opt-in only; operational emails must use send_transactional_email."""
    if not patient.email or not patient.email_marketing_opt_in:
        raise MarketingConsentRequired("O paciente nao autorizou comunicacoes promocionais por e-mail.")
    message = EmailMultiAlternatives(subject, text_body, marketing_sender(), [patient.email])
    message.attach_alternative(html_body, "text/html")
    return message.send(fail_silently=False)
