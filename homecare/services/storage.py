import shutil
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage


def safe_file_size(field_file):
    if not field_file:
        return 0, False
    try:
        if not default_storage.exists(field_file.name):
            return 0, True
        return field_file.size, False
    except (OSError, ValueError):
        return 0, True


def build_homecare_storage_usage(videos):
    local_video_bytes = 0
    temporary_bytes = 0
    thumbnail_bytes = 0
    local_video_count = 0
    temporary_count = 0
    thumbnail_count = 0
    missing_files = 0

    for video in videos:
        size, missing = safe_file_size(video.local_video_file)
        if size:
            local_video_bytes += size
            local_video_count += 1
        missing_files += int(missing)

        size, missing = safe_file_size(video.temporary_file)
        if size:
            temporary_bytes += size
            temporary_count += 1
        missing_files += int(missing)

        size, missing = safe_file_size(video.thumbnail)
        if size:
            thumbnail_bytes += size
            thumbnail_count += 1
        missing_files += int(missing)

    module_bytes = local_video_bytes + temporary_bytes + thumbnail_bytes
    average_video_bytes = local_video_bytes // local_video_count if local_video_count else 0
    disk_total_bytes = 0
    disk_free_bytes = 0
    disk_used_bytes = 0

    try:
        media_root = Path(settings.MEDIA_ROOT)
        disk_target = media_root if media_root.exists() else media_root.parent
        disk_usage = shutil.disk_usage(disk_target)
        disk_total_bytes = disk_usage.total
        disk_free_bytes = disk_usage.free
        disk_used_bytes = disk_usage.used
    except OSError:
        pass

    disk_used_percent = round((disk_used_bytes / disk_total_bytes) * 100, 1) if disk_total_bytes else 0
    module_percent = round((module_bytes / disk_total_bytes) * 100, 3) if disk_total_bytes else 0
    estimated_new_videos = int((disk_free_bytes * 0.8) // average_video_bytes) if average_video_bytes else None

    if disk_total_bytes and disk_free_bytes / disk_total_bytes < 0.10:
        status = "critical"
    elif disk_total_bytes and disk_free_bytes / disk_total_bytes < 0.20:
        status = "warning"
    else:
        status = "ok"

    return {
        "provider": getattr(settings, "HOMECARE_VIDEO_PROVIDER", "local"),
        "local_video_bytes": local_video_bytes,
        "local_video_count": local_video_count,
        "temporary_bytes": temporary_bytes,
        "temporary_count": temporary_count,
        "thumbnail_bytes": thumbnail_bytes,
        "thumbnail_count": thumbnail_count,
        "module_bytes": module_bytes,
        "missing_files": missing_files,
        "average_video_bytes": average_video_bytes,
        "disk_total_bytes": disk_total_bytes,
        "disk_used_bytes": disk_used_bytes,
        "disk_free_bytes": disk_free_bytes,
        "disk_used_percent": disk_used_percent,
        "module_percent": module_percent,
        "estimated_new_videos": estimated_new_videos,
        "status": status,
    }
