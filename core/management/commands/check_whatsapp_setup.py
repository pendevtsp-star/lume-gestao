from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.integrations.http import IntegrationError
from core.integrations.whatsapp import (
    send_whatsapp_text,
    whatsapp_runtime_state,
    whatsapp_web_gateway_status,
)
from core.models import WhatsAppIntegration, WhatsAppMessageTemplate


class Command(BaseCommand):
    help = "Valida a configuracao do WhatsApp Web sem expor tokens."

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Opcional: envia ou simula mensagem para este numero.")
        parser.add_argument("--message", default="Teste de integracao WhatsApp | Lume Gestao")
        parser.add_argument(
            "--allow-live",
            action="store_true",
            help="Permite envio real quando WHATSAPP_DRY_RUN=False. Sem isso, o comando so faz diagnostico.",
        )

    def handle(self, *args, **options):
        integration = WhatsAppIntegration.load()
        templates = WhatsAppMessageTemplate.ensure_defaults()
        state = whatsapp_runtime_state(integration, templates)
        gateway = whatsapp_web_gateway_status()

        self.stdout.write("[whatsapp] Provedor: WhatsApp Web")
        self.stdout.write(f"[whatsapp] Integracao ativa: {'sim' if integration.enabled else 'nao'}")
        self.stdout.write(f"[whatsapp] Modo teste: {'sim' if state['dry_run'] else 'nao'}")
        self.stdout.write(f"[whatsapp] Numero da clinica: {integration.clinic_whatsapp_number or '-'}")
        self.stdout.write(f"[whatsapp] Gateway Web configurado: {'sim' if settings.WHATSAPP_WEB_GATEWAY_URL else 'nao'}")
        self.stdout.write(f"[whatsapp] Sessao Web conectada: {'sim' if gateway.get('ready') else 'nao'}")
        self.stdout.write(f"[whatsapp] Modelos ativos: {state['active_templates_total']}")
        self.stdout.write(f"[whatsapp] Status operacional: {state['label']}")
        self.stdout.write(f"[whatsapp] Proximo passo: {state['next_step']}")

        if not integration.is_connected:
            self.stdout.write("[whatsapp] Ainda nao conectado. Ative a integracao, salve o numero e escaneie o QR.")
        else:
            self.stdout.write(self.style.SUCCESS("[whatsapp] Status conectado para WhatsApp Web."))

        recipient = (options.get("to") or "").strip()
        if not recipient:
            return
        if not state["dry_run"] and not options["allow_live"]:
            raise CommandError(
                "Envio real bloqueado pelo comando. Use --allow-live apenas depois de validar numero e sessao Web."
            )

        try:
            result = send_whatsapp_text(recipient, options["message"], integration=integration)
        except IntegrationError as exc:
            raise CommandError(f"Falha no teste de WhatsApp Web: {exc}") from exc

        if result.get("dry_run"):
            mode = "simulada"
        elif result.get("provider") == "whatsapp_web":
            mode = "enviada pelo WhatsApp Web"
        else:
            mode = "enviada"
        self.stdout.write(self.style.SUCCESS(f"[whatsapp] Mensagem {mode} para {result.get('to', recipient)}."))
