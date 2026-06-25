from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envia um e-mail de teste usando a configuracao SMTP atual."

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="E-mail que deve receber o teste.")

    def handle(self, *args, **options):
        recipient = options["recipient"].strip()
        if not recipient or "@" not in recipient:
            raise CommandError("Informe um e-mail de destino valido.")

        sent = send_mail(
            subject="Teste de e-mail | Lume Gestao",
            message=(
                "Este e-mail confirma que a configuracao de envio do Lume Gestao "
                "esta funcionando neste ambiente."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        if sent != 1:
            raise CommandError("O provedor de e-mail nao confirmou o envio.")

        self.stdout.write(self.style.SUCCESS(f"E-mail de teste enviado para {recipient}."))
