from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from core.integrations.credentials import configured_value
from core.integrations.http import IntegrationError
from core.integrations.whatsapp import (
    send_whatsapp_text,
    whatsapp_embedded_signup_configured,
    whatsapp_embedded_signup_credentials,
)
from core.models import WhatsAppIntegration


class Command(BaseCommand):
    help = "Valida a configuracao do WhatsApp sem expor tokens."

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Opcional: envia ou simula mensagem para este numero.")
        parser.add_argument("--message", default="Teste de integracao WhatsApp | Lume Gestao")

    def handle(self, *args, **options):
        integration = WhatsAppIntegration.load()
        app_id, config_id, app_secret = whatsapp_embedded_signup_credentials(integration)
        meta_token_configured = bool(configured_value(integration.access_token) or configured_value(settings.WHATSAPP_META_ACCESS_TOKEN))
        phone_number_id_configured = bool(
            configured_value(integration.phone_number_id) or configured_value(settings.WHATSAPP_META_PHONE_NUMBER_ID)
        )
        webhook_token_configured = bool(configured_value(settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN))
        webhook_base_url = (settings.SYSTEM_BASE_URL or settings.PUBLIC_BASE_URL or "https://sistema.clinicafisiolume.com.br").rstrip("/")
        webhook_url = f"{webhook_base_url}{reverse('whatsapp_webhook')}"

        self.stdout.write(f"[whatsapp] Provedor: {integration.get_provider_display()}")
        self.stdout.write(f"[whatsapp] Integracao ativa: {'sim' if integration.enabled else 'nao'}")
        self.stdout.write(f"[whatsapp] Modo teste: {'sim' if integration.dry_run or settings.WHATSAPP_DRY_RUN else 'nao'}")
        self.stdout.write(f"[whatsapp] Numero da clinica: {integration.clinic_whatsapp_number or '-'}")
        self.stdout.write(f"[whatsapp] Phone Number ID configurado: {'sim' if phone_number_id_configured else 'nao'}")
        self.stdout.write(f"[whatsapp] Token Meta configurado: {'sim' if meta_token_configured else 'nao'}")
        self.stdout.write(f"[whatsapp] Webhook Meta URL: {webhook_url}")
        self.stdout.write(f"[whatsapp] Verify Token webhook configurado: {'sim' if webhook_token_configured else 'nao'}")
        self.stdout.write(f"[whatsapp] Embedded Signup: {'sim' if whatsapp_embedded_signup_configured(integration) else 'nao'}")
        self.stdout.write(f"[whatsapp] App ID: {'sim' if app_id else 'nao'}")
        self.stdout.write(f"[whatsapp] Configuration ID: {'sim' if config_id else 'nao'}")
        self.stdout.write(f"[whatsapp] App Secret: {'sim' if app_secret else 'nao'}")

        if not whatsapp_embedded_signup_configured(integration):
            self.stdout.write("[whatsapp] Configure Embedded Signup para permitir conexao por botao na tela.")

        if not integration.is_connected:
            self.stdout.write("[whatsapp] Ainda nao conectado para envio real. A tela pode conectar pela Meta ou salvar dados tecnicos.")
        else:
            self.stdout.write(self.style.SUCCESS("[whatsapp] Status conectado para o modo configurado."))

        recipient = (options.get("to") or "").strip()
        if not recipient:
            return

        try:
            result = send_whatsapp_text(recipient, options["message"], integration=integration)
        except IntegrationError as exc:
            raise CommandError(f"Falha no teste de WhatsApp: {exc}") from exc

        mode = "simulada" if result.get("dry_run") else "enviada"
        self.stdout.write(self.style.SUCCESS(f"[whatsapp] Mensagem {mode} para {result.get('to', recipient)}."))
