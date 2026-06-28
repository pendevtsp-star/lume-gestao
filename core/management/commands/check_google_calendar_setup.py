from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from core.integrations.google_calendar import (
    fetch_google_email,
    google_access_token,
    google_calendar_configured,
    google_oauth_credentials,
    sync_upcoming_appointments,
)
from core.integrations.http import IntegrationError
from core.models import GoogleCalendarIntegration


class Command(BaseCommand):
    help = "Valida a configuracao do Google Agenda sem expor segredos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Se a conta estiver conectada, sincroniza os proximos agendamentos.",
        )

    def handle(self, *args, **options):
        integration = GoogleCalendarIntegration.load()
        client_id, client_secret = google_oauth_credentials(integration)
        base_url = (settings.PUBLIC_BASE_URL or settings.SYSTEM_BASE_URL or "http://127.0.0.1:8000").rstrip("/")
        callback_url = f"{base_url}{reverse('integrations_google_callback')}"

        self.stdout.write(f"[google] Callback: {callback_url}")
        self.stdout.write(f"[google] Client ID configurado: {'sim' if client_id else 'nao'}")
        self.stdout.write(f"[google] Client Secret configurado: {'sim' if client_secret else 'nao'}")
        self.stdout.write(f"[google] Conta conectada: {integration.connected_email or '-'}")
        self.stdout.write(f"[google] Agenda: {integration.calendar_id or 'primary'}")

        if not google_calendar_configured():
            raise CommandError("Google Calendar ainda nao possui Client ID e Client Secret validos.")

        if integration.is_connected:
            try:
                google_access_token(integration)
                email = fetch_google_email(integration)
            except IntegrationError as exc:
                raise CommandError(f"Conta Google conectada, mas a validacao falhou: {exc}") from exc
            if email and email != integration.connected_email:
                integration.connected_email = email
                integration.save(update_fields=["connected_email", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"[google] OAuth validado para {email or integration.connected_email}."))
        else:
            self.stdout.write("[google] Credenciais prontas. Conecte a conta pela tela de integracoes.")

        if options["sync"]:
            if not integration.is_connected:
                raise CommandError("Use --sync apenas depois de conectar uma conta Google.")
            synced, failed = sync_upcoming_appointments()
            if failed:
                raise CommandError(f"Sincronizacao parcial: {synced} enviado(s), {failed} falha(s).")
            self.stdout.write(self.style.SUCCESS(f"[google] Sincronizacao concluida: {synced} agendamento(s)."))
