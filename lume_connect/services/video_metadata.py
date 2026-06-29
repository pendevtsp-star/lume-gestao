from io import BytesIO


class VideoMetadataError(ValueError):
    pass


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
