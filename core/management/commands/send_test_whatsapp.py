from django.core.management.base import BaseCommand, CommandError

from core.integrations.http import IntegrationError
from core.integrations.whatsapp import send_whatsapp_text


class Command(BaseCommand):
    help = "Envia ou simula uma mensagem WhatsApp usando a integracao configurada."

    def add_arguments(self, parser):
        parser.add_argument("number", help="Numero de destino, com ou sem DDI.")
        parser.add_argument(
            "--message",
            default="Teste de mensagem do Lume Gestao.",
            help="Mensagem de teste.",
        )

    def handle(self, *args, **options):
        try:
            result = send_whatsapp_text(options["number"], options["message"])
        except IntegrationError as exc:
            raise CommandError(str(exc)) from exc

        mode = "simulada" if result.get("dry_run") else "enviada"
        self.stdout.write(self.style.SUCCESS(f"Mensagem WhatsApp {mode} para {result.get('to', options['number'])}."))
