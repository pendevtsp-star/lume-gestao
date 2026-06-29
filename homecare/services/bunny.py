from pathlib import Path
from uuid import uuid4
from urllib import error, request

from django.core.files.base import File
from django.core.files.storage import default_storage
from django.conf import settings
from django.utils.text import slugify

from core.integrations.credentials import first_configured_value
from core.integrations.http import IntegrationError, post_json


def bunny_configured():
    return bool(first_configured_value(settings.BUNNY_STREAM_API_KEY) and first_configured_value(settings.BUNNY_STREAM_LIBRARY_ID))


def bunny_headers():
    api_key = first_configured_value(settings.BUNNY_STREAM_API_KEY)
    if not api_key:
        raise IntegrationError("Configure BUNNY_STREAM_API_KEY no .env.")
    return {"AccessKey": api_key}


def create_bunny_video(video):
    library_id = first_configured_value(settings.BUNNY_STREAM_LIBRARY_ID)
    if not library_id:
        raise IntegrationError("Configure BUNNY_STREAM_LIBRARY_ID no .env.")
    if settings.BUNNY_STREAM_DRY_RUN:
        return {
            "guid": f"dry-run-{video.pk}",
            "libraryId": library_id,
            "embedUrl": f"https://iframe.mediadelivery.net/embed/{library_id}/dry-run-{video.pk}",
            "dry_run": True,
        }
    return post_json(
        f"https://video.bunnycdn.com/library/{library_id}/videos",
        {"title": video.title},
        headers=bunny_headers(),
        timeout=settings.BUNNY_STREAM_TIMEOUT,
    )


def upload_bunny_video_file(video, provider_video_id):
    library_id = first_configured_value(settings.BUNNY_STREAM_LIBRARY_ID)
    if not library_id:
        raise IntegrationError("Configure BUNNY_STREAM_LIBRARY_ID no .env.")
    if not video.temporary_file:
        raise IntegrationError("Selecione um arquivo de video para enviar.")
    file_path = Path(video.temporary_file.path)
    if not file_path.exists():
        raise IntegrationError("Arquivo temporario de video nao encontrado.")
    if settings.BUNNY_STREAM_DRY_RUN:
        return {"success": True, "dry_run": True}

    url = f"https://video.bunnycdn.com/library/{library_id}/videos/{provider_video_id}"
    try:
        with file_path.open("rb") as file_handle:
            headers = {"Content-Type": "application/octet-stream", **bunny_headers()}
            req = request.Request(url, data=file_handle, headers=headers, method="PUT")
            with request.urlopen(req, timeout=settings.BUNNY_STREAM_TIMEOUT) as response:
                body = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise IntegrationError(f"HTTP {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise IntegrationError(str(exc.reason)) from exc
    return {"success": True, "response": body}


def build_bunny_embed_url(video):
    if video.provider_embed_url:
        return video.provider_embed_url
    library_id = video.provider_library_id or first_configured_value(settings.BUNNY_STREAM_LIBRARY_ID)
    if not library_id or not video.provider_video_id:
        return ""
    return f"https://iframe.mediadelivery.net/embed/{library_id}/{video.provider_video_id}"


def upload_provider():
    provider = (settings.HOMECARE_VIDEO_PROVIDER or "local").lower()
    return provider if provider in {"local", "bunny"} else "local"


def local_video_target_name(video, source_path):
    extension = source_path.suffix.lower() or ".mp4"
    slug = slugify(video.slug or video.title) or f"video-{video.pk}"
    return f"{video.pk}/{slug}-{uuid4().hex[:10]}{extension}"


def process_local_video_file(video):
    if not video.temporary_file:
        raise IntegrationError("Selecione um arquivo de video para salvar.")
    file_path = Path(video.temporary_file.path)
    if not file_path.exists():
        raise IntegrationError("Arquivo temporario de video nao encontrado.")

    previous_local_name = video.local_video_file.name if video.local_video_file else ""
    target_name = local_video_target_name(video, file_path)
    with file_path.open("rb") as file_handle:
        video.local_video_file.save(target_name, File(file_handle), save=False)

    if previous_local_name and previous_local_name != video.local_video_file.name:
        default_storage.delete(previous_local_name)

    return {
        "success": True,
        "storage": "local",
        "path": video.local_video_file.name,
        "size": video.local_video_file.size,
    }


def process_upload_job(job):
    if upload_provider() == "local":
        return process_local_upload_job(job)
    return process_bunny_upload_job(job)


def process_local_upload_job(job):
    video = job.video
    job.status = job.Status.RUNNING
    job.attempts += 1
    job.error_message = ""
    from django.utils import timezone

    job.started_at = timezone.now()
    job.save(update_fields=["status", "attempts", "error_message", "started_at", "updated_at"])

    video.status = video.Status.UPLOADING
    video.upload_error = ""
    video.save(update_fields=["status", "upload_error", "updated_at"])

    try:
        upload_result = process_local_video_file(video)
    except Exception as exc:
        job.status = job.Status.FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        video.status = video.Status.FAILED
        video.upload_error = str(exc)
        video.save(update_fields=["status", "upload_error", "updated_at"])
        return False

    video.provider = video.Provider.LOCAL
    video.provider_video_id = f"local-{video.pk}-{uuid4().hex[:10]}"
    video.provider_library_id = ""
    video.provider_embed_url = ""
    video.provider_payload = {"local": upload_result}
    video.status = video.Status.READY
    video.upload_error = ""
    video.save(
        update_fields=[
            "provider",
            "provider_video_id",
            "provider_library_id",
            "provider_embed_url",
            "provider_payload",
            "local_video_file",
            "status",
            "upload_error",
            "updated_at",
        ]
    )
    if video.temporary_file:
        video.temporary_file.delete(save=False)
        video.temporary_file = ""
        video.save(update_fields=["temporary_file", "updated_at"])

    job.status = job.Status.DONE
    job.finished_at = timezone.now()
    job.error_message = ""
    job.save(update_fields=["status", "finished_at", "error_message", "updated_at"])
    return True


def process_bunny_upload_job(job):
    video = job.video
    job.status = job.Status.RUNNING
    job.attempts += 1
    job.error_message = ""
    from django.utils import timezone

    job.started_at = timezone.now()
    job.save(update_fields=["status", "attempts", "error_message", "started_at", "updated_at"])

    video.status = video.Status.UPLOADING
    video.upload_error = ""
    video.save(update_fields=["status", "upload_error", "updated_at"])

    try:
        created = create_bunny_video(video)
        provider_video_id = created.get("guid") or created.get("videoId") or created.get("id")
        if not provider_video_id:
            raise IntegrationError("Bunny nao retornou ID do video.")
        upload_result = upload_bunny_video_file(video, provider_video_id)
    except Exception as exc:
        job.status = job.Status.FAILED
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        video.status = video.Status.FAILED
        video.upload_error = str(exc)
        video.save(update_fields=["status", "upload_error", "updated_at"])
        return False

    library_id = str(created.get("libraryId") or first_configured_value(settings.BUNNY_STREAM_LIBRARY_ID))
    video.provider = video.Provider.BUNNY
    video.provider_video_id = str(provider_video_id)
    video.provider_library_id = library_id
    video.provider_embed_url = created.get("embedUrl") or build_bunny_embed_url(video)
    video.provider_payload = {"create": created, "upload": upload_result}
    video.status = video.Status.READY
    video.upload_error = ""
    video.save(
        update_fields=[
            "provider",
            "provider_video_id",
            "provider_library_id",
            "provider_embed_url",
            "provider_payload",
            "status",
            "upload_error",
            "updated_at",
        ]
    )
    if video.temporary_file:
        video.temporary_file.delete(save=False)
        video.temporary_file = ""
        video.save(update_fields=["temporary_file", "updated_at"])

    job.status = job.Status.DONE
    job.finished_at = timezone.now()
    job.error_message = ""
    job.save(update_fields=["status", "finished_at", "error_message", "updated_at"])
    return True
