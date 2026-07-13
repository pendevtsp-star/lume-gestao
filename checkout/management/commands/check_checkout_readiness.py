from io import StringIO

from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.test.utils import override_settings

from checkout.providers import checkout_gateway_status


class Command(BaseCommand):
    help = "Mostra a prontidao segura do checkout Asaas e pode executar a homologacao dry-run sem alterar o .env."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verify-dry-run",
            action="store_true",
            help="Executa a homologacao local em dry-run com flags temporarias, sem chamar o Asaas nem manter dados.",
        )

    def handle(self, *args, **options):
        gateway = checkout_gateway_status()
        self.stdout.write("Prontidao do Checkout Asaas")
        self.stdout.write(f"- Provider: {gateway['provider_code']}")
        self.stdout.write(f"- Modo: {gateway['mode_label']}")
        self.stdout.write(f"- Conta recebedora: {gateway['merchant_status_label']}")
        self.stdout.write(
            "- Credenciais: API {} | webhook {}".format(
                "configurada" if gateway["api_key_configured"] else "pendente",
                "configurado" if gateway["webhook_token_configured"] else "pendente",
            )
        )

        if gateway["can_run_dry_run"]:
            self.stdout.write(self.style.SUCCESS("- Homologacao local: pronta"))
        else:
            blockers = ", ".join(gateway["dry_run_blockers"]) or "provider ou modo dry-run"
            self.stdout.write(self.style.WARNING(f"- Homologacao local: pendente ({blockers})"))

        if gateway["readiness"] == "ready":
            self.stdout.write(self.style.SUCCESS("- Cobranca remota: pronta para a etapa controlada"))
        else:
            self.stdout.write("- Cobranca remota: bloqueada ate configurar credenciais, webhook e conta recebedora.")

        if options["verify_dry_run"]:
            self.stdout.write("\nExecutando homologacao local isolada...")
            self._run_isolated_dry_run()
            self.stdout.write(self.style.SUCCESS("Homologacao local isolada: concluida sem alterar o .env."))

    def _run_isolated_dry_run(self):
        temporary_settings = {
            "CHECKOUT_ENABLED": True,
            "CHECKOUT_PUBLIC_ENABLED": True,
            "CHECKOUT_PATIENT_ENABLED": True,
            "CHECKOUT_WEBHOOK_ENABLED": True,
            "CHECKOUT_PAYMENT_PROVIDER": "asaas",
            "CHECKOUT_REQUIRE_MERCHANT_ACCOUNT": False,
            "ASAAS_DRY_RUN": True,
            "ASAAS_API_KEY": settings.ASAAS_API_KEY,
            "ASAAS_WEBHOOK_TOKEN": settings.ASAAS_WEBHOOK_TOKEN or "dry-run-local-token",
        }
        output = StringIO()
        with override_settings(**temporary_settings):
            call_command("homologate_checkout_dry_run", stdout=output)
        self.stdout.write(output.getvalue().rstrip())
