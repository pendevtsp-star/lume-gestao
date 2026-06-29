from django.core.management.base import BaseCommand

from core.deletion import cleanup_pending_deletions
from core.integrations.whatsapp import process_scheduled_whatsapp_messages
from core.services.whatsapp_automation import enqueue_automatic_whatsapp_messages


class Command(BaseCommand):
    help = "Processa a fila de mensagens WhatsApp agendadas."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Quantidade maxima de mensagens por execucao.")

    def handle(self, *args, **options):
        cleanup = cleanup_pending_deletions(limit=options["limit"])
        automation = enqueue_automatic_whatsapp_messages(limit=options["limit"])
        summary = process_scheduled_whatsapp_messages(limit=options["limit"])
        if options.get("verbosity", 1) > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "Fila WhatsApp processada: "
                    f"{automation['appointment']} consulta(s) automatica(s), "
                    f"{automation['birthday']} aniversario(s) automatico(s), "
                    f"{automation['membership_due']} mensalidade(s) a vencer, "
                    f"{automation['membership_overdue']} mensalidade(s) vencida(s), "
                    f"{automation['charge_overdue']} cobranca(s) avulsa(s) vencida(s), "
                    f"{cleanup['deleted']} exclusao(oes) pendente(s), "
                    f"{summary['processed']} item(ns), "
                    f"{summary['sent']} enviado(s), "
                    f"{summary['dry_run']} simulado(s), "
                    f"{summary['failed']} falha(s)."
                )
            )
