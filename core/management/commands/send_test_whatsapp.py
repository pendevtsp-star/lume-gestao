from django.core.management.base import BaseCommand, CommandError

from core.integrations.http import IntegrationError
from core.integrations.whatsapp import send_whatsapp_text, whatsapp_runtime_state
from core.models import WhatsAppIntegration


class Command(BaseCommand):
    help = "Envia ou simula uma mensagem WhatsApp usando a integracao configurada."

    def add_arguments(self, parser):
        parser.add_argument("number", help="Numero de destino, com ou sem DDI.")
        parser.add_argument(
            "--message",
            default="Teste de mensagem do Lume Gestao.",
            help="Mensagem de teste.",
        )
        parser.add_argument(
            "--allow-live",
            action="store_true",
            help="Permite envio real quando a integracao nao estiver em modo teste.",
        )

    def handle(self, *args, **options):
        integration = WhatsAppIntegration.load()
        state = whatsapp_runtime_state(integration)
        if not state["dry_run"] and not options["allow_live"]:
            raise CommandError(
                "Envio real bloqueado. Use --allow-live apenas para teste controlado com numero autorizado."
            )
        try:
            result = send_whatsapp_text(options["number"], options["message"], integration=integration)
        except IntegrationError as exc:
            raise CommandError(str(exc)) from exc

        if result.get("dry_run"):
            mode = "simulada"
        elif result.get("provider") == "whatsapp_web":
            mode = "enviada pelo WhatsApp Web"
        else:
            mode = "enviada"
        self.stdout.write(self.style.SUCCESS(f"Mensagem WhatsApp {mode} para {result.get('to', options['number'])}."))
