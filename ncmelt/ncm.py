"""Netease Cloud Music (.ncm) container reader.

The format is a small encrypted header followed by the original audio stream.
No Netease service or network access is involved; everything is local.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import threading
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from Crypto.Cipher import AES
from Crypto.Util.strxor import strxor

from .errors import ConversionCancelled, NCMFormatError, NCMTruncatedError

MAGIC = b"CTENFDAM"
CORE_KEY = bytes.fromhex("687A4852416D736F356B496E62617857")  # hzHRAmso5kInbaxW
META_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")  # #14ljk_!\]&0U<'(
KEY_PREFIX = b"neteasecloudmusic"
META_PREFIX = b"163 key(Don't modify):"
MUSIC_PREFIX = b"music:"

_READ_CHUNK = 1024 * 1024
_MAX_KEY_BYTES = 1024 * 1024
_MAX_META_BYTES = 16 * 1024 * 1024
_MAX_COVER_BYTES = 64 * 1024 * 1024

FORMAT_LABELS = {
    "mp3": "MP3",
    "flac": "FLAC",
    "aac": "AAC",
    "m4a": "M4A",
    "ogg": "OGG",
    "wav": "WAV",
    "ape": "APE",
    "wma": "WMA",
    "bin": "音频",
}

LOSSLESS_FORMATS = {"flac", "ape", "wav"}


class _HeaderReader:
    """Reads and validates the encrypted NCM header."""

    def __init__(self, fh, path: Path):
        self.fh = fh
        self.path = path
        self.warnings: list[str] = []

    def _read(self, size: int, what: str) -> bytes:
        data = self.fh.read(size)
        if len(data) != size:
            raise NCMTruncatedError(f"{what}读取不完整，文件可能已损坏")
        return data

    def _u32(self, what: str) -> int:
        return struct.unpack("<I", self._read(4, what))[0]

    def read(self) -> "NCMHeader":
        if self._read(8, "文件头") != MAGIC:
            raise NCMFormatError("文件头不是 CTENFDAM，可能不是网易云 NCM 文件")

        version = self.fh.read(2)
        if len(version) != 2:
            raise NCMTruncatedError("NCM 版本信息读取失败")
        ncm_version, client_version = version[0], version[1]

        key_len = self._u32("密钥长度")
        if key_len <= 0 or key_len > _MAX_KEY_BYTES:
            raise NCMFormatError("NCM 密钥长度异常")
        encrypted_key = self._read(key_len, "密钥")
        content_key = self._decrypt_content_key(encrypted_key)
        key_stream = build_key_stream(content_key)

        meta_len = self._u32("元数据长度")
        if meta_len < 0 or meta_len > _MAX_META_BYTES:
            raise NCMFormatError("NCM 元数据长度异常")
        encrypted_meta = self._read(meta_len, "元数据")
        metadata = self._decrypt_metadata(encrypted_meta) if meta_len else None

        meta_end = self.fh.tell()
        expected_crc = self._u32("校验码")
        actual_crc = self._crc32_prefix(meta_end)
        if expected_crc and actual_crc != expected_crc:
            self.warnings.append("文件头校验码不一致，已尝试继续转换")

        cover_version = self._read(1, "封面版本")[0]
        if cover_version != 1:
            self.warnings.append(f"未知的封面版本 {cover_version}，已尝试继续转换")

        cover_frame_len = self._u32("封面区长度")
        if cover_frame_len > _MAX_COVER_BYTES:
            raise NCMFormatError("NCM 封面数据异常")
        cover_len = self._u32("封面长度")
        if cover_len > cover_frame_len:
            raise NCMFormatError("NCM 封面长度异常")

        cover = self._read(cover_len, "封面") if cover_len else b""
        extra_cover_len = cover_frame_len - cover_len
        if extra_cover_len:
            # Some clients store a second image; it is not needed for MP3 tags.
            self._read(extra_cover_len, "附加封面")

        audio_offset = self.fh.tell()
        size = os.fstat(self.fh.fileno()).st_size
        if audio_offset >= size:
            raise NCMTruncatedError("NCM 文件中没有音频数据")

        prefix = self.fh.read(16)
        if not prefix:
            raise NCMTruncatedError("NCM 文件中没有音频数据")
        self.fh.seek(audio_offset)

        hint = (metadata.format if metadata else "") or ""
        container = detect_container(prefix, hint)
        if container == "bin" and hint:
            container = hint

        return NCMHeader(
            path=self.path,
            metadata=metadata,
            key_stream=key_stream,
            cover=cover,
            cover_mime=detect_image_mime(cover),
            audio_offset=audio_offset,
            file_size=size,
            audio_size=size - audio_offset,
            container=container,
            warnings=self.warnings,
            ncm_version=ncm_version,
            client_version=client_version,
        )

    def _decrypt_content_key(self, encrypted: bytes) -> bytes:
        data = bytes(b ^ 0x64 for b in encrypted)
        try:
            decrypted = AES.new(CORE_KEY, AES.MODE_ECB).decrypt(data)
        except ValueError as exc:
            raise NCMFormatError("NCM 密钥解密失败") from exc
        decrypted = unpad_pkcs7(decrypted)
        if decrypted.startswith(KEY_PREFIX):
            key = decrypted[len(KEY_PREFIX) :]
        else:
            # A few broken files omit the marker. The historical format always
            # uses a 17-byte prefix, so keep compatibility with those files.
            key = decrypted[17:] if len(decrypted) > 17 else b""
            self.warnings.append("NCM 密钥缺少标准前缀，已尝试兼容处理")
        if not key:
            raise NCMFormatError("NCM 密钥为空")
        return key

    def _decrypt_metadata(self, encrypted: bytes) -> "NCMMetadata | None":
        data = bytes(b ^ 0x63 for b in encrypted)
        if data.startswith(META_PREFIX):
            data = data[len(META_PREFIX) :]
        try:
            decoded = base64.b64decode(data, validate=False)
            decrypted = AES.new(META_KEY, AES.MODE_ECB).decrypt(decoded)
        except (ValueError, TypeError) as exc:
            raise NCMFormatError("NCM 元数据解密失败") from exc
        decrypted = unpad_pkcs7(decrypted)
        if decrypted.startswith(MUSIC_PREFIX):
            decrypted = decrypted[len(MUSIC_PREFIX) :]
        text = decrypted.decode("utf-8", errors="replace").strip("\x00\r\n\t ")
        if not text:
            return None
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            self.warnings.append("NCM 元数据不是有效的 JSON，将使用文件名")
            return None
        if not isinstance(raw, dict):
            return None
        return NCMMetadata.from_json(raw)

    def _crc32_prefix(self, end: int) -> int:
        current = self.fh.tell()
        try:
            self.fh.seek(0)
            crc = 0
            remaining = end
            while remaining:
                block = self.fh.read(min(_READ_CHUNK, remaining))
                if not block:
                    break
                crc = zlib.crc32(block, crc)
                remaining -= len(block)
            return crc & 0xFFFFFFFF
        finally:
            self.fh.seek(current)


@dataclass
class NCMMetadata:
    title: str = ""
    artists: list[str] = field(default_factory=list)
    album: str = ""
    bitrate: int = 0
    duration_ms: int = 0
    format: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "NCMMetadata":
        title = _string(raw.get("musicName") or raw.get("name") or raw.get("title"))
        album = _string(raw.get("album"))
        artists: list[str] = []
        raw_artists = raw.get("artist") or raw.get("artists") or []
        if isinstance(raw_artists, list):
            for entry in raw_artists:
                if isinstance(entry, (list, tuple)) and entry:
                    name = _string(entry[0])
                else:
                    name = _string(entry)
                if name and name not in artists:
                    artists.append(name)
        elif isinstance(raw_artists, str) and raw_artists.strip():
            artists = [raw_artists.strip()]

        bitrate = _positive_int(raw.get("bitrate"))
        duration = _positive_int(raw.get("duration"))
        # Netease stores milliseconds. A handful of older caches stored seconds.
        if 0 < duration < 3600:
            duration *= 1000
        fmt = _string(raw.get("format")).lower().lstrip(".")
        if fmt == "m4a":
            fmt = "m4a"
        return cls(
            title=title,
            artists=artists,
            album=album,
            bitrate=bitrate,
            duration_ms=duration,
            format=fmt,
            raw=raw,
        )

    @property
    def artist_text(self) -> str:
        return " / ".join(self.artists)

    @property
    def display_title(self) -> str:
        return self.title or "未命名歌曲"

    @property
    def is_lossless(self) -> bool:
        return self.format in LOSSLESS_FORMATS

    @property
    def quality_text(self) -> str:
        if self.is_lossless:
            return "无损"
        if self.bitrate > 0:
            return f"{round(self.bitrate / 1000)} kbps"
        return "未知码率"

    @property
    def duration_text(self) -> str:
        if self.duration_ms <= 0:
            return "--:--"
        total = round(self.duration_ms / 1000)
        minutes, seconds = divmod(total, 60)
        return f"{minutes:02d}:{seconds:02d}"


@dataclass
class NCMHeader:
    path: Path
    metadata: NCMMetadata | None
    key_stream: bytes
    cover: bytes
    cover_mime: str
    audio_offset: int
    file_size: int
    audio_size: int
    container: str
    warnings: list[str] = field(default_factory=list)
    ncm_version: int = 1
    client_version: int = 0

    @property
    def format_label(self) -> str:
        return FORMAT_LABELS.get(self.container, self.container.upper() or "音频")

    @property
    def is_lossless(self) -> bool:
        return self.container in LOSSLESS_FORMATS

    @property
    def has_audio(self) -> bool:
        return self.audio_size > 0


@dataclass
class ExtractedAudio:
    path: Path
    container: str
    audio_size: int
    header: NCMHeader


class NCMFile:
    """Reader for one .ncm file."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)

    def inspect(self) -> NCMHeader:
        if not self.path.is_file():
            raise NCMFormatError("文件不存在")
        try:
            with self.path.open("rb") as fh:
                return _HeaderReader(fh, self.path).read()
        except OSError as exc:
            raise NCMFormatError(f"无法读取文件：{exc}") from exc

    def extract(
        self,
        dest_dir: str | os.PathLike[str],
        progress: Callable[[int, int], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ExtractedAudio:
        """Decrypt the audio stream into *dest_dir* and return its path."""
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("rb") as src:
                header = _HeaderReader(src, self.path).read()
                if cancel_event is not None and cancel_event.is_set():
                    raise ConversionCancelled()
                suffix = header.container if header.container != "bin" else "bin"
                out_path = dest / f"decrypted.{suffix}"
                total = header.audio_size
                done = 0
                stream = header.key_stream
                src.seek(header.audio_offset)
                try:
                    with out_path.open("wb") as out:
                        while True:
                            if cancel_event is not None and cancel_event.is_set():
                                raise ConversionCancelled()
                            chunk = src.read(_READ_CHUNK)
                            if not chunk:
                                break
                            shift = done % 256
                            rotated = stream[shift:] + stream[:shift]
                            repeats = (len(chunk) + 255) // 256
                            key_material = (rotated * repeats)[: len(chunk)]
                            out.write(strxor(chunk, key_material))
                            done += len(chunk)
                            if progress is not None:
                                progress(done, total)
                    if done == 0:
                        raise NCMTruncatedError("没有解密出音频数据")
                    if out_path.stat().st_size < 64:
                        raise NCMTruncatedError("解密出的音频数据过短")
                    return ExtractedAudio(
                        path=out_path,
                        container=header.container,
                        audio_size=done,
                        header=header,
                    )
                except BaseException:
                    try:
                        out_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    raise
        except OSError as exc:
            raise NCMFormatError(f"读取或写入文件失败：{exc}") from exc


def inspect_ncm(path: str | os.PathLike[str]) -> NCMHeader:
    return NCMFile(path).inspect()


def build_key_stream(content_key: bytes) -> bytes:
    """Build the 256-byte XOR stream used by Netease's audio cipher."""
    if not content_key:
        raise NCMFormatError("NCM 音频密钥为空")
    box = list(range(256))
    j = 0
    key_len = len(content_key)
    for i in range(256):
        j = (j + box[i] + content_key[i % key_len]) & 0xFF
        box[i], box[j] = box[j], box[i]
    out = bytearray(256)
    for i in range(256):
        i2 = (i + 1) & 0xFF
        j = (box[i2] + i2) & 0xFF
        out[i] = box[(box[i2] + box[j]) & 0xFF]
    return bytes(out)


def detect_container(prefix: bytes, hint: str = "") -> str:
    if prefix.startswith(b"fLaC"):
        return "flac"
    if prefix.startswith(b"ID3"):
        return "mp3"
    if len(prefix) >= 2 and prefix[0] == 0xFF and (prefix[1] & 0xF6) == 0xF0:
        return "aac"
    if len(prefix) >= 2 and prefix[0] == 0xFF and (prefix[1] & 0xE0) == 0xE0:
        return "mp3"
    if prefix.startswith(b"OggS"):
        return "ogg"
    if prefix.startswith(b"RIFF") and prefix[8:12] == b"WAVE":
        return "wav"
    if len(prefix) >= 8 and prefix[4:8] == b"ftyp":
        return "m4a"
    if prefix.startswith(b"MAC "):
        return "ape"
    if prefix.startswith(bytes.fromhex("3026B275")):
        return "wma"
    hint = (hint or "").lower().lstrip(".")
    if hint in FORMAT_LABELS:
        return hint
    return "bin"


def detect_image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def unpad_pkcs7(data: bytes) -> bytes:
    if not data:
        return data
    pad = data[-1]
    if 1 <= pad <= 16 and data.endswith(bytes([pad]) * pad):
        return data[:-pad]
    return data.rstrip(b"\x00")


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return " / ".join(str(v) for v in value if v)
    return str(value).strip()


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0
