"""Audio encoding, tagging and validation powered by FFmpeg."""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from .errors import (
    ConversionCancelled,
    FFmpegError,
    FFmpegNotFoundError,
    OutputError,
)
from .formats import (
    DEFAULT_FORMAT,
    FORMAT_BY_ID,
    OutputFormat,
    QualityOption,
    format_by_id,
    quality_for,
)

LOG = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_PROGRESS_INTERVAL = 0.05

__all__ = [
    "FORMATS",
    "MediaResult",
    "OutputFormat",
    "QualityOption",
    "DEFAULT_FORMAT",
    "find_ffmpeg",
    "ffmpeg_version",
    "format_by_id",
    "quality_for",
    "transcode_to_format",
    "open_in_explorer",
]

FORMATS = FORMAT_BY_ID


@dataclass
class MediaResult:
    path: Path
    format_id: str
    bitrate_kbps: int
    duration_seconds: float
    sample_rate: int
    channels: int
    size_bytes: int
    lossless: bool


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _ffmpeg_candidates() -> list[Path]:
    candidates: list[Path] = []
    env_value = os.environ.get("NCMELT_FFMPEG", "").strip().strip('"')
    if env_value:
        candidates.append(Path(env_value))
    base = app_base_dir()
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.extend(
            [
                Path(meipass) / "ffmpeg.exe",
                Path(meipass) / "bin" / "ffmpeg.exe",
                Path(meipass) / "assets" / "ffmpeg.exe",
            ]
        )
    candidates.extend(
        [
            base / "ffmpeg.exe",
            base / "bin" / "ffmpeg.exe",
            base / "assets" / "ffmpeg.exe",
            Path(__file__).resolve().parent / "ffmpeg.exe",
        ]
    )
    which = shutil.which("ffmpeg")
    if which:
        candidates.append(Path(which))
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except OSError:
            key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


_ffmpeg_cache: Path | None = None
_ffmpeg_version_cache: str | None = None


def _ffmpeg_version_from_output(output: str) -> str:
    first_line = output.splitlines()[0] if output else "FFmpeg"
    match = re.search(r"ffmpeg version\s+n?(\d+(?:\.\d+)*)", first_line)
    return f"FFmpeg {match.group(1)}" if match else "FFmpeg 已就绪"


def find_ffmpeg() -> Path:
    """Locate a usable FFmpeg executable next to the app or on PATH."""
    global _ffmpeg_cache, _ffmpeg_version_cache
    if _ffmpeg_cache is not None and _ffmpeg_cache.exists():
        return _ffmpeg_cache
    for candidate in _ffmpeg_candidates():
        if not candidate.is_file():
            continue
        try:
            completed = subprocess.run(
                [str(candidate), "-hide_banner", "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0:
            _ffmpeg_cache = candidate
            # Reuse this probe for the status bar; a second subprocess was
            # adding noticeable startup latency on Windows.
            _ffmpeg_version_cache = _ffmpeg_version_from_output(completed.stdout or "")
            return candidate
    raise FFmpegNotFoundError(
        "找不到可用的 FFmpeg。请确认程序目录中的 ffmpeg.exe 未被删除。"
    )


def ffmpeg_version() -> str:
    global _ffmpeg_version_cache
    if _ffmpeg_version_cache:
        return _ffmpeg_version_cache
    try:
        ffmpeg = find_ffmpeg()
        if _ffmpeg_version_cache:
            return _ffmpeg_version_cache
        result = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        _ffmpeg_version_cache = _ffmpeg_version_from_output(result.stdout or "")
    except (FFmpegNotFoundError, OSError, subprocess.SubprocessError):
        _ffmpeg_version_cache = "FFmpeg 未就绪"
    return _ffmpeg_version_cache


def transcode_to_format(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    format_id: str,
    quality_id: str | None = None,
    *,
    title: str = "",
    artist: str = "",
    album: str = "",
    cover: bytes = b"",
    cover_mime: str = "image/jpeg",
    duration_ms: int = 0,
    write_tags: bool = True,
    embed_cover: bool = True,
    progress: Callable[[float], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> MediaResult:
    """Encode *source* to the requested output format.

    Output is written to a temporary file, tagged, fully decoded for
    validation, and only then atomically moved to *destination*.
    """
    fmt = format_by_id(format_id)
    quality = fmt.quality(quality_id)
    source_path = Path(source)
    dest_path = Path(destination)
    if not source_path.is_file():
        raise FFmpegError("待转码的音频不存在")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()

    fd, temp_name = tempfile.mkstemp(
        prefix=".ncmelt-", suffix="." + fmt.extension, dir=str(dest_path.parent)
    )
    os.close(fd)
    temp_path = Path(temp_name)
    total_seconds = max(0.0, duration_ms / 1000.0)

    try:
        _run_encode(
            ffmpeg,
            source_path,
            temp_path,
            fmt,
            quality,
            total_seconds=total_seconds,
            progress=progress,
            cancel_event=cancel_event,
        )
        if cancel_event is not None and cancel_event.is_set():
            raise ConversionCancelled("已取消转换")
        _validate_output(ffmpeg, temp_path, cancel_event=cancel_event)
        if write_tags:
            try:
                tag_media(
                    temp_path,
                    fmt,
                    title=title,
                    artist=artist,
                    album=album,
                    cover=cover if embed_cover else b"",
                    cover_mime=cover_mime,
                )
            except Exception as exc:
                # Tagging is important, but a valid audio file is more important.
                # Keep the file and surface the issue in the log rather than
                # throwing away a successfully encoded track.
                LOG.warning("Tagging failed for %s: %s", temp_path, exc)
        try:
            audio = MutagenFile(str(temp_path))
            if audio is None or audio.info is None:
                raise ValueError("mutagen could not parse the output")
        except Exception as exc:
            raise FFmpegError("生成的文件无法读取，已删除输出") from exc
        if audio.info.length <= 0.1:
            raise FFmpegError("生成的文件时长为 0，已删除输出")
        os.replace(temp_path, dest_path)
        bitrate = round((getattr(audio.info, "bitrate", 0) or 0) / 1000)
        return MediaResult(
            path=dest_path,
            format_id=fmt.id,
            bitrate_kbps=bitrate,
            duration_seconds=float(audio.info.length),
            sample_rate=int(getattr(audio.info, "sample_rate", 0) or 0),
            channels=int(getattr(audio.info, "channels", 0) or 0),
            size_bytes=dest_path.stat().st_size,
            lossless=fmt.lossless,
        )
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _run_encode(
    ffmpeg: Path,
    source: Path,
    output: Path,
    fmt: OutputFormat,
    quality: QualityOption,
    *,
    total_seconds: float,
    progress: Callable[[float], None] | None,
    cancel_event: threading.Event | None,
) -> None:
    args = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        *quality.codec_args,
    ]
    if fmt.id == "mp3":
        args.extend(["-id3v2_version", "3"])
    elif fmt.id == "m4a":
        args.extend(["-movflags", "+faststart"])
    args.append(str(output))

    LOG.info("FFmpeg encode: %s", " ".join(args))
    with tempfile.TemporaryFile(mode="w+b") as err_file:
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=err_file,
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            raise FFmpegError(f"无法启动 FFmpeg：{exc}") from exc

        cancelled = False
        last_fraction = -1.0
        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    _terminate(proc)
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    _, _, raw_value = line.partition("=")
                    try:
                        micros = int(raw_value)
                    except ValueError:
                        continue
                    if total_seconds > 0:
                        fraction = min(
                            0.995,
                            max(0.0, micros / 1_000_000.0 / total_seconds),
                        )
                        if progress is not None and (
                            fraction - last_fraction >= _PROGRESS_INTERVAL
                            or fraction >= 0.99
                        ):
                            last_fraction = fraction
                            progress(fraction)
            proc.wait()
        except BaseException:
            _terminate(proc)
            raise
        finally:
            if proc.stdout is not None:
                proc.stdout.close()

        if cancelled or (cancel_event is not None and cancel_event.is_set()):
            raise ConversionCancelled("已取消转换")

        err_file.seek(0)
        error_text = err_file.read().decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            message = _short_ffmpeg_error(error_text)
            raise FFmpegError(f"转码失败：{message}" if message else "FFmpeg 转码失败")
        if not output.is_file() or output.stat().st_size < 64:
            raise FFmpegError("FFmpeg 没有生成有效的音频文件")
        if progress is not None:
            progress(1.0)


def _validate_output(
    ffmpeg: Path, path: Path, *, cancel_event: threading.Event | None
) -> None:
    args = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-xerror",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
        )
        _, stderr = proc.communicate(timeout=240)
    except subprocess.TimeoutExpired as exc:
        _terminate(proc)
        raise FFmpegError("输出文件完整性校验超时") from exc
    except OSError as exc:
        raise FFmpegError(f"无法校验输出文件：{exc}") from exc
    if cancel_event is not None and cancel_event.is_set():
        raise ConversionCancelled("已取消转换")
    if proc.returncode != 0:
        message = (stderr or b"").decode("utf-8", errors="replace").strip()
        raise FFmpegError(
            f"生成的文件未通过完整性校验：{_short_ffmpeg_error(message)}"
        )


def tag_media(
    path: Path,
    fmt: OutputFormat,
    *,
    title: str,
    artist: str,
    album: str,
    cover: bytes,
    cover_mime: str,
) -> None:
    if fmt.id == "mp3":
        _tag_id3(path, title, artist, album, cover, cover_mime)
    elif fmt.id == "flac":
        _tag_flac(path, title, artist, album, cover, cover_mime)
    elif fmt.id == "m4a":
        _tag_mp4(path, title, artist, album, cover, cover_mime)
    elif fmt.id == "ogg":
        _tag_ogg(path, title, artist, album, cover, cover_mime)
    elif fmt.id == "wav":
        _tag_wav(path, title, artist, album, cover, cover_mime)


def _tag_id3(
    path: Path, title: str, artist: str, album: str, cover: bytes, cover_mime: str
) -> None:
    tags = ID3()
    if title:
        tags.add(TIT2(encoding=1, text=[title]))
    if artist:
        tags.add(TPE1(encoding=1, text=[artist]))
    if album:
        tags.add(TALB(encoding=1, text=[album]))
    if cover and len(cover) <= 8 * 1024 * 1024:
        tags.add(
            APIC(
                encoding=0,
                mime=cover_mime or "image/jpeg",
                type=3,
                desc="Front cover",
                data=cover,
            )
        )
    tags.save(str(path), v2_version=3)


def _flac_picture(cover: bytes, cover_mime: str) -> Picture:
    picture = Picture()
    picture.type = 3
    picture.mime = cover_mime or "image/jpeg"
    picture.desc = "Front cover"
    picture.data = cover
    return picture


def _tag_flac(
    path: Path, title: str, artist: str, album: str, cover: bytes, cover_mime: str
) -> None:
    audio = FLAC(path)
    audio.clear_pictures()
    if title:
        audio["title"] = title
    if artist:
        audio["artist"] = artist
    if album:
        audio["album"] = album
    if cover:
        audio.add_picture(_flac_picture(cover, cover_mime))
    audio.save()


def _tag_mp4(
    path: Path, title: str, artist: str, album: str, cover: bytes, cover_mime: str
) -> None:
    audio = MP4(path)
    audio["\xa9nam"] = [title] if title else []
    audio["\xa9ART"] = [artist] if artist else []
    audio["\xa9alb"] = [album] if album else []
    if cover:
        image_format = (
            MP4Cover.FORMAT_PNG if cover_mime == "image/png" else MP4Cover.FORMAT_JPEG
        )
        audio["covr"] = [MP4Cover(cover, imageformat=image_format)]
    audio.save()


def _tag_ogg(
    path: Path, title: str, artist: str, album: str, cover: bytes, cover_mime: str
) -> None:
    audio = OggVorbis(path)
    if title:
        audio["title"] = title
    if artist:
        audio["artist"] = artist
    if album:
        audio["album"] = album
    if cover:
        picture = _flac_picture(cover, cover_mime)
        audio["metadata_block_picture"] = [
            base64.b64encode(picture.write()).decode("ascii")
        ]
    audio.save()


def _tag_wav(
    path: Path, title: str, artist: str, album: str, cover: bytes, cover_mime: str
) -> None:
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    if title:
        tags.add(TIT2(encoding=1, text=[title]))
    if artist:
        tags.add(TPE1(encoding=1, text=[artist]))
    if album:
        tags.add(TALB(encoding=1, text=[album]))
    if cover:
        tags.add(
            APIC(
                encoding=0,
                mime=cover_mime or "image/jpeg",
                type=3,
                desc="Front cover",
                data=cover,
            )
        )
    audio.save()


def open_in_explorer(path: str | os.PathLike[str]) -> None:
    target = Path(path)
    if not target.exists():
        raise OutputError("输出目录不存在")
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass


def _short_ffmpeg_error(text: str, max_lines: int = 3) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    useful = [line for line in lines if not line.startswith("frame=")][-max_lines:]
    return "；".join(useful)[:500]
