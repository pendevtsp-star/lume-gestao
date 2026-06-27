from datetime import timedelta
from urllib.parse import quote, urlencode

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from core.integrations.http import IntegrationError, delete_json, get_json, patch_json, post_form, post_json
from core.models import GoogleCalendarIntegration
from scheduling.models import Appointment


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3/calendars"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
]


def google_calendar_configured():
    client_id, client_secret = google_oauth_credentials()
    return bool(client_id and client_secret)


def google_oauth_credentials(integration=None):
    integration = integration or GoogleCalendarIntegration.load()
    client_id = integration.oauth_client_id or settings.GOOGLE_CALENDAR_CLIENT_ID
    client_secret = integration.oauth_client_secret or settings.GOOGLE_CALENDAR_CLIENT_SECRET
    return client_id, client_secret


def google_redirect_uri(request):
    return request.build_absolute_uri(reverse("integrations_google_callback"))


def build_google_authorization_url(request):
    integration = GoogleCalendarIntegration.load()
    client_id, client_secret = google_oauth_credentials(integration)
    if not client_id or not client_secret:
        raise IntegrationError("Configure o Google Client ID e o Google Client Secret nos ajustes avancados da integracao.")
    state = timezone.now().strftime("%Y%m%d%H%M%S")
    request.session["google_calendar_oauth_state"] = state
    params = {
        "client_id": client_id,
        "redirect_uri": google_redirect_uri(request),
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_google_code(request, code):
    integration = GoogleCalendarIntegration.load()
    client_id, client_secret = google_oauth_credentials(integration)
    if not client_id or not client_secret:
        raise IntegrationError("Configure o Google Client ID e o Google Client Secret antes de conectar.")
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": google_redirect_uri(request),
        "grant_type": "authorization_code",
    }
    token_data = post_form(GOOGLE_TOKEN_URL, payload, timeout=settings.GOOGLE_CALENDAR_TIMEOUT)
    _update_tokens(integration, token_data)
    integration.enabled = True
    integration.last_error = ""
    integration.connected_email = fetch_google_email(integration)
    integration.save()
    return integration


def fetch_google_email(integration):
    data = get_json(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {integration.access_token}"},
        timeout=settings.GOOGLE_CALENDAR_TIMEOUT,
    )
    return data.get("email", "")


def refresh_google_token(integration):
    if not integration.refresh_token:
        raise IntegrationError("Conecte a conta Google Agenda novamente.")
    client_id, client_secret = google_oauth_credentials(integration)
    if not client_id or not client_secret:
        raise IntegrationError("Configure o Google Client ID e o Google Client Secret nos ajustes da integracao.")
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": integration.refresh_token,
        "grant_type": "refresh_token",
    }
    token_data = post_form(GOOGLE_TOKEN_URL, payload, timeout=settings.GOOGLE_CALENDAR_TIMEOUT)
    _update_tokens(integration, token_data)
    integration.save(update_fields=["access_token", "refresh_token", "token_expires_at", "updated_at"])
    return integration.access_token


def _update_tokens(integration, token_data):
    integration.access_token = token_data.get("access_token", integration.access_token)
    integration.refresh_token = token_data.get("refresh_token", integration.refresh_token)
    expires_in = int(token_data.get("expires_in", 3600))
    integration.token_expires_at = timezone.now() + timedelta(seconds=max(expires_in - 60, 60))


def google_access_token(integration):
    if not integration.access_token or not integration.token_expires_at or integration.token_expires_at <= timezone.now():
        return refresh_google_token(integration)
    return integration.access_token


def appointment_event_payload(appointment):
    return {
        "summary": f"{appointment.patient.full_name} - {appointment.professional.full_name}",
        "description": f"Status: {appointment.get_status_display()}\nObservacoes: {appointment.notes or '-'}",
        "start": {"dateTime": appointment.starts_at.isoformat()},
        "end": {"dateTime": appointment.ends_at.isoformat()},
    }


def delete_google_event(event_id, integration=None):
    integration = integration or GoogleCalendarIntegration.load()
    if not integration.is_connected:
        raise IntegrationError("Google Agenda ainda nao esta conectado.")

    token = google_access_token(integration)
    calendar_id = integration.calendar_id or "primary"
    encoded_calendar_id = quote(calendar_id, safe="")
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GOOGLE_CALENDAR_BASE_URL}/{encoded_calendar_id}/events/{event_id}"
    delete_json(url, headers=headers, timeout=settings.GOOGLE_CALENDAR_TIMEOUT)


def clear_google_tracking(appointment):
    appointment.external_provider = ""
    appointment.external_event_id = ""
    appointment._skip_google_sync = True
    appointment.save(update_fields=["external_provider", "external_event_id", "updated_at"])
    appointment._skip_google_sync = False


def sync_appointment_to_google(appointment, integration=None):
    integration = integration or GoogleCalendarIntegration.load()
    if not integration.is_connected:
        raise IntegrationError("Google Agenda ainda nao esta conectado.")

    token = google_access_token(integration)
    calendar_id = integration.calendar_id or "primary"
    encoded_calendar_id = quote(calendar_id, safe="")
    headers = {"Authorization": f"Bearer {token}"}
    payload = appointment_event_payload(appointment)

    if appointment.status in {Appointment.Status.CANCELED, Appointment.Status.RESCHEDULED} and appointment.external_event_id:
        delete_google_event(appointment.external_event_id, integration=integration)
        clear_google_tracking(appointment)
        return None

    if appointment.external_provider == "google" and appointment.external_event_id:
        url = f"{GOOGLE_CALENDAR_BASE_URL}/{encoded_calendar_id}/events/{appointment.external_event_id}"
        method_payload = {**payload}
        event = patch_json(url, method_payload, headers=headers, timeout=settings.GOOGLE_CALENDAR_TIMEOUT)
    else:
        url = f"{GOOGLE_CALENDAR_BASE_URL}/{encoded_calendar_id}/events"
        event = post_json(url, payload, headers=headers, timeout=settings.GOOGLE_CALENDAR_TIMEOUT)
        appointment.external_provider = "google"
        appointment.external_event_id = event.get("id", "")
        appointment._skip_google_sync = True
        appointment.save(update_fields=["external_provider", "external_event_id", "updated_at"])
        appointment._skip_google_sync = False
    return event


def sync_upcoming_appointments(days=90):
    integration = GoogleCalendarIntegration.load()
    start = timezone.now()
    end = start + timedelta(days=days)
    synced = 0
    failed = 0
    appointments = Appointment.objects.select_related("patient", "professional").filter(
        starts_at__gte=start,
        starts_at__lte=end,
    )
    for appointment in appointments:
        try:
            sync_appointment_to_google(appointment, integration=integration)
            synced += 1
        except IntegrationError as exc:
            failed += 1
            integration.last_error = str(exc)
            integration.save(update_fields=["last_error", "updated_at"])
    integration.last_sync_at = timezone.now()
    integration.save(update_fields=["last_sync_at", "last_error", "updated_at"])
    return synced, failed
