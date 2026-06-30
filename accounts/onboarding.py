from dataclasses import dataclass
from secrets import choice
from unicodedata import normalize

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from core.integrations.http import IntegrationError
from core.integrations.whatsapp import send_whatsapp_text


PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789@#$%+-"


@dataclass
class PatientOnboardingResult:
    user: object
    created: bool
    username: str
    temporary_password: str
    delivery_channel: str = ""
    delivery_error: str = ""

    @property
    def delivered(self):
        return self.delivery_channel in {"email", "whatsapp"}


def normalize_username_part(value):
    normalized = normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(character.lower() for character in normalized if character.isalnum())
    return cleaned or "paciente"


def username_base_from_name(full_name, fallback="usuario"):
    parts = [normalize_username_part(part) for part in (full_name or "").split() if part]
    parts = [part for part in parts if part]
    if len(parts) >= 2:
        return f"{parts[0]}{parts[-1]}"
    if parts:
        return parts[0]
    return normalize_username_part(fallback)


def generate_unique_username(full_name, fallback="usuario", exclude_user=None):
    user_model = get_user_model()
    base = username_base_from_name(full_name, fallback=fallback)
    username = base
    suffix = 2
    queryset = user_model.objects.all()
    if exclude_user and getattr(exclude_user, "pk", None):
        queryset = queryset.exclude(pk=exclude_user.pk)
    while queryset.filter(username__iexact=username).exists():
        username = f"{base}{suffix}"
        suffix += 1
    return username


def generate_patient_username(patient):
    return generate_unique_username(patient.full_name, fallback="paciente")


def generate_temporary_password(length=12):
    return "".join(choice(PASSWORD_ALPHABET) for _ in range(length))


def split_name(full_name):
    parts = [part for part in (full_name or "").split() if part]
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def build_login_url(request=None):
    path = reverse("login")
    if request:
        return request.build_absolute_uri(path)
    if settings.PUBLIC_BASE_URL:
        return f"{settings.PUBLIC_BASE_URL.rstrip('/')}{path}"
    return path


def welcome_message_text(patient, username, temporary_password, login_url):
    return (
        f"Ola, {patient.full_name}! Seja bem-vindo(a) ao Lume Gestao.\n\n"
        "Criamos seu acesso para acompanhar informacoes da clinica, agenda e dados do seu atendimento.\n"
        f"Login: {username}\n"
        f"Senha temporaria: {temporary_password}\n"
        f"Acesse: {login_url}\n\n"
        "Por seguranca, o sistema vai pedir a troca da senha no primeiro acesso. "
        "A equipe Lume deseja que sua experiencia seja leve, organizada e acolhedora."
    )


def send_patient_welcome_email(patient, username, temporary_password, login_url):
    context = {
        "patient": patient,
        "username": username,
        "temporary_password": temporary_password,
        "login_url": login_url,
    }
    subject = render_to_string("accounts/email/welcome_patient_subject.txt", context).strip()
    text_body = render_to_string("accounts/email/welcome_patient.txt", context)
    html_body = render_to_string("accounts/email/welcome_patient.html", context)
    message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [patient.email])
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)


def send_user_welcome_email(user, temporary_password, login_url):
    context = {
        "display_name": user.get_full_name() or user.username,
        "username": user.username,
        "temporary_password": temporary_password,
        "login_url": login_url,
    }
    subject = render_to_string("accounts/email/welcome_user_subject.txt", context).strip()
    text_body = render_to_string("accounts/email/welcome_user.txt", context)
    html_body = render_to_string("accounts/email/welcome_user.html", context)
    message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)


def send_patient_welcome_whatsapp(patient, username, temporary_password, login_url):
    result = send_whatsapp_text(
        patient.phone,
        welcome_message_text(patient, username, temporary_password, login_url),
    )
    return "whatsapp_simulado" if result.get("dry_run") else "whatsapp"


def deliver_patient_credentials(patient, username, temporary_password, request=None):
    login_url = build_login_url(request)
    if patient.email:
        try:
            send_patient_welcome_email(patient, username, temporary_password, login_url)
            return "email", ""
        except Exception as exc:
            email_error = str(exc)
        if patient.phone:
            try:
                channel = send_patient_welcome_whatsapp(patient, username, temporary_password, login_url)
                return channel, email_error if channel == "whatsapp_simulado" else ""
            except IntegrationError as exc:
                return "", f"{email_error}; WhatsApp: {exc}"
        return "", email_error

    if patient.phone:
        try:
            channel = send_patient_welcome_whatsapp(patient, username, temporary_password, login_url)
            return channel, "" if channel == "whatsapp" else "WhatsApp em modo teste; mensagem nao enviada de verdade."
        except IntegrationError as exc:
            return "", str(exc)

    return "", "Paciente sem e-mail e sem WhatsApp cadastrado."


def ensure_patient_user(patient, request=None, send_notifications=True):
    existing_profile = getattr(patient, "user_profile", None)
    if existing_profile and existing_profile.user_id:
        return PatientOnboardingResult(
            user=existing_profile.user,
            created=False,
            username=existing_profile.user.username,
            temporary_password="",
        )

    user_model = get_user_model()
    username = generate_patient_username(patient)
    temporary_password = generate_temporary_password()
    first_name, last_name = split_name(patient.full_name)
    user = user_model.objects.create_user(
        username=username,
        email=patient.email or "",
        password=temporary_password,
        first_name=first_name,
        last_name=last_name,
    )
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = UserProfile.Role.PATIENT
    profile.patient = patient
    profile.phone = patient.phone
    profile.must_change_password = True
    profile.save()

    delivery_channel = ""
    delivery_error = ""
    if send_notifications:
        delivery_channel, delivery_error = deliver_patient_credentials(
            patient,
            username,
            temporary_password,
            request=request,
        )

    return PatientOnboardingResult(
        user=user,
        created=True,
        username=username,
        temporary_password=temporary_password,
        delivery_channel=delivery_channel,
        delivery_error=delivery_error,
    )


def send_welcome_credentials(user, temporary_password, request=None, phone_number="", prefer_email=True):
    profile = user.profile
    patient = profile.patient
    if not patient:
        if prefer_email and user.email:
            try:
                send_user_welcome_email(user, temporary_password, build_login_url(request))
            except Exception as exc:
                profile.onboarding_delivery_method = ""
                profile.onboarding_delivery_error = str(exc)
                profile.save(update_fields=["onboarding_delivery_method", "onboarding_delivery_error", "updated_at"])
                return {"sent": False, "method": "", "error": profile.onboarding_delivery_error}
            profile.onboarding_message_sent_at = timezone.now()
            profile.onboarding_delivery_method = "email"
            profile.onboarding_delivery_error = ""
            profile.save(
                update_fields=[
                    "onboarding_message_sent_at",
                    "onboarding_delivery_method",
                    "onboarding_delivery_error",
                    "updated_at",
                ]
            )
            return {"sent": True, "method": "email", "error": ""}
        return {"sent": False, "method": "", "error": "Usuario sem e-mail para envio automatico."}

    original_email = patient.email
    original_phone = patient.phone
    if not prefer_email:
        patient.email = ""
    if phone_number:
        patient.phone = phone_number

    try:
        channel, error = deliver_patient_credentials(patient, user.username, temporary_password, request=request)
    finally:
        patient.email = original_email
        patient.phone = original_phone

    if channel == "email":
        profile.onboarding_message_sent_at = timezone.now()
        profile.onboarding_delivery_method = "email"
        profile.onboarding_delivery_error = ""
        profile.save(
            update_fields=[
                "onboarding_message_sent_at",
                "onboarding_delivery_method",
                "onboarding_delivery_error",
                "updated_at",
            ]
        )
        return {"sent": True, "method": "email", "error": ""}
    if channel == "whatsapp":
        profile.onboarding_message_sent_at = timezone.now()
        profile.onboarding_delivery_method = "whatsapp"
        profile.onboarding_delivery_error = ""
        profile.save(
            update_fields=[
                "onboarding_message_sent_at",
                "onboarding_delivery_method",
                "onboarding_delivery_error",
                "updated_at",
            ]
        )
        return {"sent": True, "method": "whatsapp", "error": ""}

    profile.onboarding_delivery_method = ""
    profile.onboarding_delivery_error = error or "Nao foi possivel entregar as credenciais."
    profile.save(update_fields=["onboarding_delivery_method", "onboarding_delivery_error", "updated_at"])
    return {"sent": False, "method": "", "error": profile.onboarding_delivery_error}
