from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from homecare.models import HomecareUploadJob
from homecare.services.bunny import process_upload_job


class Command(BaseCommand):
    help = "Processa uploads pendentes do modulo Fisioterapia em Casa."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5, help="Quantidade maxima de uploads por execucao.")

    def handle(self, *args, **options):
        if not settings.HOMECARE_UPLOAD_WORKER_ENABLED:
            raise CommandError("Processamento de uploads do Fisioterapia em Casa esta desabilitado.")
        jobs = list(
            HomecareUploadJob.objects.select_related("video")
            .filter(status=HomecareUploadJob.Status.QUEUED)
            .order_by("created_at")[: options["limit"]]
        )
        processed = 0
        failed = 0
        for job in jobs:
            if process_upload_job(job):
                processed += 1
            else:
                failed += 1
        if options.get("verbosity", 1) > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Uploads Fisioterapia em Casa: {processed} concluido(s), {failed} falha(s)."
                )
            )
