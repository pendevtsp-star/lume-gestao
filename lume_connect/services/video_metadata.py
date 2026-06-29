import json
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


class VideoProcessingError(ValueError):
    pass


@dataclass
class VideoMetadata:
    duration_seconds: float
    format_name: str = ""
    codec_name: str = ""
    width: int | None = None
    height: int | None = None


@dataclass
class ProcessedVideo:
    video_bytes: bytes
    video_name: str
    video_size_bytes: int
    duration_seconds: float
    thumbnail_bytes: bytes | None = None
    thumbnail_name: str | None = None


def _read_u32(data):
    return int.from_bytes(data, "big")


def _read_u64(data):
    return int.from_bytes(data, "big")


def _iter_mp4_boxes(stream, end):
    while stream.tell() + 8 <= end:
        start = stream.tell()
        header = stream.read(8)
        if len(header) < 8:
            return
        size = _read_u32(header[:4])
        box_type = header[4:8]
        header_size = 8
        if size == 1:
            largesize = stream.read(8)
            if len(largesize) < 8:
                return
            size = _read_u64(largesize)
            header_size = 16
        elif size == 0:
            size = end - start
        if size < header_size:
            return
        yield box_type, start + header_size, start + size
        stream.seek(start + size)


def _duration_from_mvhd(stream, payload_start, payload_end):
    stream.seek(payload_start)
    header = stream.read(4)
    if len(header) < 4:
        return None
    version = header[0]
    if version == 1:
        stream.seek(payload_start + 4 + 8 + 8)
        raw_timescale = stream.read(4)
        raw_duration = stream.read(8)
        if len(raw_timescale) < 4 or len(raw_duration) < 8:
            return None
        timescale = _read_u32(raw_timescale)
        duration = _read_u64(raw_duration)
    else:
        stream.seek(payload_start + 4 + 4 + 4)
        raw_timescale = stream.read(4)
        raw_duration = stream.read(4)
        if len(raw_timescale) < 4 or len(raw_duration) < 4:
            return None
        timescale = _read_u32(raw_timescale)
        duration = _read_u32(raw_duration)
    if not timescale:
        return None
    return duration / timescale


def _find_duration(stream, start, end):
    for box_type, payload_start, payload_end in _iter_mp4_boxes(stream, end):
        if box_type == b"mvhd":
            return _duration_from_mvhd(stream, payload_start, payload_end)
        if box_type in {b"moov", b"trak", b"mdia"}:
            stream.seek(payload_start)
            duration = _find_duration(stream, payload_start, payload_end)
            if duration is not None:
                return duration
    return None


def get_mp4_duration_seconds(uploaded_file):
    from io import BytesIO

    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else None
    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
        if not data:
            return None
        stream = BytesIO(data)
        duration = _find_duration(stream, 0, len(data))
        if duration is None:
            return None
        return round(duration, 2)
    finally:
        if position is not None:
            uploaded_file.seek(position)


def build_test_mp4(duration_seconds, timescale=1000):
    duration_units = int(duration_seconds * timescale)
    mvhd_payload = (
        b"\x00\x00\x00\x00"
        + (0).to_bytes(4, "big")
        + (0).to_bytes(4, "big")
        + timescale.to_bytes(4, "big")
        + duration_units.to_bytes(4, "big")
        + b"\x00" * 80
    )
    mvhd = (len(mvhd_payload) + 8).to_bytes(4, "big") + b"mvhd" + mvhd_payload
    moov = (len(mvhd) + 8).to_bytes(4, "big") + b"moov" + mvhd
    ftyp_payload = b"isom\x00\x00\x02\x00isommp42"
    ftyp = (len(ftyp_payload) + 8).to_bytes(4, "big") + b"ftyp" + ftyp_payload
    mdat_payload = b"\x00" * 32
    mdat = (len(mdat_payload) + 8).to_bytes(4, "big") + b"mdat" + mdat_payload
    return ftyp + moov + mdat


def _write_upload_to_temp(uploaded_file, suffix, directory):
    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else None
    try:
        uploaded_file.seek(0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=directory) as temp_file:
            for chunk in uploaded_file.chunks() if hasattr(uploaded_file, "chunks") else [uploaded_file.read()]:
                temp_file.write(chunk)
            return Path(temp_file.name)
    finally:
        if position is not None:
            uploaded_file.seek(position)


def _run_command(command, error_message):
    timeout = getattr(settings, "LUME_CONNECT_FFMPEG_TIMEOUT_SECONDS", 120)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise VideoProcessingError("FFmpeg/ffprobe nao esta instalado ou nao foi encontrado no PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise VideoProcessingError("O processamento do video excedeu o tempo limite.") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise VideoProcessingError(f"{error_message} {detail}".strip())
    return completed


def _probe_path(path):
    ffprobe_path = getattr(settings, "LUME_CONNECT_FFPROBE_PATH", "ffprobe")
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    completed = _run_command(command, "Nao foi possivel ler os metadados do video.")
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise VideoProcessingError("ffprobe retornou metadados invalidos para o video.") from exc
    video_stream = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"), None)
    if not video_stream:
        raise VideoProcessingError("O arquivo enviado nao contem uma faixa de video valida.")
    duration = video_stream.get("duration") or payload.get("format", {}).get("duration")
    try:
        duration_seconds = round(float(duration), 2)
    except (TypeError, ValueError) as exc:
        raise VideoProcessingError("Nao foi possivel confirmar a duracao do video.") from exc
    return VideoMetadata(
        duration_seconds=duration_seconds,
        format_name=payload.get("format", {}).get("format_name", ""),
        codec_name=video_stream.get("codec_name", ""),
        width=video_stream.get("width"),
        height=video_stream.get("height"),
    )


def probe_video(uploaded_file):
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else "video"
    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = _write_upload_to_temp(uploaded_file, f".{extension}", temp_dir)
        try:
            return _probe_path(input_path)
        finally:
            input_path.unlink(missing_ok=True)


def process_short_video_upload(uploaded_file, metadata=None, generate_thumbnail=True):
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else "video"
    ffmpeg_path = getattr(settings, "LUME_CONNECT_FFMPEG_PATH", "ffmpeg")
    max_width = getattr(settings, "LUME_CONNECT_TRANSCODE_MAX_WIDTH", 720)
    crf = getattr(settings, "LUME_CONNECT_TRANSCODE_CRF", 28)
    preset = getattr(settings, "LUME_CONNECT_TRANSCODE_PRESET", "veryfast")
    audio_bitrate = getattr(settings, "LUME_CONNECT_TRANSCODE_AUDIO_BITRATE", "96k")
    output_stem = uuid.uuid4().hex

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = _write_upload_to_temp(uploaded_file, f".{extension}", temp_dir)
        output_path = Path(temp_dir) / f"{output_stem}.mp4"
        thumbnail_path = Path(temp_dir) / f"{output_stem}.jpg"
        try:
            metadata = metadata or _probe_path(input_path)
            scale_filter = f"scale=min({max_width}\\,iw):-2"
            command = [
                ffmpeg_path,
                "-y",
                "-i",
                str(input_path),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-vf",
                scale_filter,
                "-c:v",
                "libx264",
                "-preset",
                str(preset),
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                str(audio_bitrate),
                "-ac",
                "2",
                str(output_path),
            ]
            _run_command(command, "Nao foi possivel otimizar o video.")
            thumbnail_bytes = None
            thumbnail_name = None
            if generate_thumbnail:
                timestamp = min(1.0, max(0.0, metadata.duration_seconds / 2))
                thumb_command = [
                    ffmpeg_path,
                    "-y",
                    "-ss",
                    str(timestamp),
                    "-i",
                    str(input_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    scale_filter,
                    "-q:v",
                    "3",
                    str(thumbnail_path),
                ]
                _run_command(thumb_command, "Nao foi possivel gerar a capa do video.")
                thumbnail_bytes = thumbnail_path.read_bytes()
                thumbnail_name = f"{output_stem}.jpg"
            video_bytes = output_path.read_bytes()
            return ProcessedVideo(
                video_bytes=video_bytes,
                video_name=f"{output_stem}.mp4",
                video_size_bytes=len(video_bytes),
                duration_seconds=metadata.duration_seconds,
                thumbnail_bytes=thumbnail_bytes,
                thumbnail_name=thumbnail_name,
            )
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
            thumbnail_path.unlink(missing_ok=True)
