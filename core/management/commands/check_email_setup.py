from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Valida a configuracao de e-mail sem expor segredos."

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Opcional: envia um e-mail real de validacao para este destino.")

    def handle(self, *args, **options):
        recipient = (options.get("to") or "").strip()
        backend = settings.EMAIL_BACKEND

        self.stdout.write(f"[email] Backend: {backend}")
        self.stdout.write(f"[email] Remetente: {settings.DEFAULT_FROM_EMAIL}")

        if "smtp" in backend.lower():
            self.stdout.write(f"[email] Host SMTP: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
            self.stdout.write(f"[email] TLS: {'sim' if settings.EMAIL_USE_TLS else 'nao'}")
            if not settings.EMAIL_HOST:
                raise CommandError("EMAIL_HOST nao esta configurado.")
            if not settings.EMAIL_HOST_USER:
                raise CommandError("EMAIL_HOST_USER nao esta configurado.")
            if not settings.EMAIL_HOST_PASSWORD:
                raise CommandError("EMAIL_HOST_PASSWORD nao esta configurado.")

        try:
            connection = get_connection(fail_silently=False)
            connection.open()
        except Exception as exc:
            raise CommandError(f"Nao foi possivel abrir a conexao de e-mail: {exc}") from exc

        if recipient:
            if "@" not in recipient:
                raise CommandError("Informe um e-mail de destino valido.")
            message = EmailMessage(
                subject="Validacao de e-mail | Lume Gestao",
                body=(
                    "Este e-mail confirma que o Lume Gestao conseguiu abrir conexao "
                    "com o provedor e enviar uma mensagem de validacao."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                connection=connection,
            )
            if message.send() != 1:
                raise CommandError("O provedor de e-mail nao confirmou o envio.")
            self.stdout.write(self.style.SUCCESS(f"[email] E-mail enviado para {recipient}."))
        else:
            self.stdout.write(self.style.SUCCESS("[email] Conexao validada. Use --to para testar entrega real."))
