"""High-level NCM -> audio conversion workflow."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import OutputError
from .formats import OutputFormat, QualityOption, format_by_id, quality_for
from .ncm import NCMFile, NCMHeader
from .transcoder import MediaResult, transcode_to_format

LOG = logging.getLogger(__name__)

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
_WINDOWS_MAX_NAME = 150


@dataclass
class ConversionOutcome:
    source: Path
    output: Path
    header: NCMHeader
    media: MediaResult
    output_format: OutputFormat
    quality: QualityOption
    elapsed_seconds: float


def convert_ncm(
    source: str | os.PathLike[str],
    output_dir: str | os.PathLike[str] | None,
    format_id: str,
    quality_id: str | None = None,
    *,
    destination: str | os.PathLike[str] | None = None,
    overwrite: bool = False,
    naming: str = "artist-title",
    overwrite_existing: bool = False,
    write_tags: bool = True,
    embed_cover: bool = True,
    cancel_event: threading.Event | None = None,
    on_stage: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> ConversionOutcome:
    """Convert one NCM file.

    ``on_progress`` receives a fraction from 0 to 1 covering both decryption
    and encoding. ``on_stage`` receives ``"decrypt"``, ``"encode"`` or
    ``"verify"``.
    """
    started = time.monotonic()
    src = Path(source)
    fmt = format_by_id(format_id)
    quality = fmt.quality(quality_id)
    if cancel_event is not None and cancel_event.is_set():
        from .errors import ConversionCancelled

        raise ConversionCancelled("已取消转换")

    if on_stage is not None:
        on_stage("decrypt")
    if on_progress is not None:
        on_progress(0.0)

    reader = NCMFile(src)
    header = reader.inspect()
    if destination is not None:
        output_path = Path(destination)
        target_dir = output_path.parent
        if output_path.exists() and not overwrite:
            raise OutputError(f"输出文件已存在：{output_path}")
    else:
        target_dir = Path(output_dir) if output_dir else src.parent
        output_path = build_output_path(
            src,
            header,
            target_dir,
            fmt,
            naming=naming,
            overwrite_existing=overwrite_existing,
        )
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"无法创建输出目录：{exc}") from exc

    with tempfile.TemporaryDirectory(prefix=".ncmelt-", dir=str(target_dir)) as temp_dir:

        def extraction_progress(done: int, total: int) -> None:
            if on_progress is not None and total > 0:
                on_progress(min(0.18, 0.18 * done / total))

        extracted = reader.extract(
            temp_dir, progress=extraction_progress, cancel_event=cancel_event
        )
        if on_stage is not None:
            on_stage("encode")
        if on_progress is not None:
            on_progress(0.18)

        metadata = extracted.header.metadata
        title = metadata.display_title if metadata else src.stem
        artist = metadata.artist_text if metadata else ""
        album = metadata.album if metadata else ""
        duration_ms = metadata.duration_ms if metadata else 0
        if duration_ms <= 0:
            try:
                from mutagen import File as MutagenFile

                probe = MutagenFile(str(extracted.path))
                if probe is not None and probe.info.length:
                    duration_ms = int(float(probe.info.length) * 1000)
            except Exception:
                LOG.debug("Could not probe duration for %s", extracted.path, exc_info=True)
                duration_ms = 0

        def encode_progress(fraction: float) -> None:
            if on_progress is not None:
                on_progress(0.18 + 0.82 * max(0.0, min(1.0, fraction)))

        media = transcode_to_format(
            extracted.path,
            output_path,
            fmt.id,
            quality.id,
            title=title,
            artist=artist,
            album=album,
            cover=extracted.header.cover,
            cover_mime=extracted.header.cover_mime,
            duration_ms=duration_ms,
            write_tags=write_tags,
            embed_cover=embed_cover,
            progress=encode_progress,
            cancel_event=cancel_event,
        )
        if on_stage is not None:
            on_stage("verify")
        if on_progress is not None:
            on_progress(1.0)

    elapsed = time.monotonic() - started
    LOG.info("Converted %s -> %s in %.2fs", src, output_path, elapsed)
    return ConversionOutcome(
        source=src,
        output=output_path,
        header=header,
        media=media,
        output_format=fmt,
        quality=quality,
        elapsed_seconds=elapsed,
    )


def build_output_path(
    source: Path,
    header: NCMHeader,
    target_dir: Path,
    fmt: OutputFormat | str,
    *,
    naming: str = "artist-title",
    overwrite_existing: bool = False,
) -> Path:
    output_format = fmt if isinstance(fmt, OutputFormat) else format_by_id(fmt)
    metadata = header.metadata
    if metadata:
        title = metadata.display_title
        artist = metadata.artist_text
    else:
        title, artist = source.stem, ""
    if naming == "title":
        base = title
    elif artist and artist.casefold() not in title.casefold():
        base = f"{artist} - {title}"
    else:
        base = title
    base = sanitize_filename(base) or sanitize_filename(source.stem) or "未命名歌曲"
    candidate = target_dir / f"{base}.{output_format.extension}"
    if overwrite_existing or not candidate.exists():
        return candidate
    for index in range(1, 1000):
        candidate = target_dir / f"{base} ({index}).{output_format.extension}"
        if not candidate.exists():
            return candidate
    raise OutputError("同名文件过多，请更换输出目录")


def sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name)
    name = _INVALID_FILENAME.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return ""
    stem = name.split(".", 1)[0].strip().casefold()
    if stem in _RESERVED_NAMES:
        name = f"_{name}"
    if len(name) > _WINDOWS_MAX_NAME:
        name = name[:_WINDOWS_MAX_NAME].rstrip(" .")
    return name


def probe_source(source: str | os.PathLike[str]) -> NCMHeader:
    return NCMFile(source).inspect()


def quality_for_output(format_id: str, quality_id: str | None) -> QualityOption:
    return quality_for(format_id, quality_id)
