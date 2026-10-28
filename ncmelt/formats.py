"""Output format and quality definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityOption:
    id: str
    label: str
    description: str
    bitrate_kbps: int | None = None
    lossless: bool = False
    codec_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class OutputFormat:
    id: str
    label: str
    extension: str
    description: str
    qualities: tuple[QualityOption, ...]
    default_quality: str
    lossless: bool = False

    def quality(self, quality_id: str | None) -> QualityOption:
        for option in self.qualities:
            if option.id == quality_id:
                return option
        for option in self.qualities:
            if option.id == self.default_quality:
                return option
        return self.qualities[0]

    @property
    def default_quality_option(self) -> QualityOption:
        return self.quality(self.default_quality)


MP3 = OutputFormat(
    id="mp3",
    label="MP3",
    extension="mp3",
    description="兼容性最好，固定或动态码率",
    default_quality="320",
    qualities=(
        QualityOption("320", "320 kbps", "固定码率 · 细节最完整", 320, False, ("-c:a", "libmp3lame", "-b:a", "320k")),
        QualityOption("256", "256 kbps", "固定码率 · 音质与体积均衡", 256, False, ("-c:a", "libmp3lame", "-b:a", "256k")),
        QualityOption("192", "192 kbps", "固定码率 · 日常收听", 192, False, ("-c:a", "libmp3lame", "-b:a", "192k")),
        QualityOption("128", "128 kbps", "固定码率 · 体积最小", 128, False, ("-c:a", "libmp3lame", "-b:a", "128k")),
        QualityOption("v0", "V0 动态", "可变码率 · 平均约 245 kbps", 245, False, ("-c:a", "libmp3lame", "-q:a", "0")),
    ),
)

FLAC = OutputFormat(
    id="flac",
    label="FLAC",
    extension="flac",
    description="无损压缩，保留完整音频细节",
    default_quality="standard",
    lossless=True,
    qualities=(
        QualityOption("standard", "标准压缩", "无损 · 推荐", None, True, ("-c:a", "flac", "-compression_level", "5")),
        QualityOption("max", "最高压缩", "无损 · 文件略小、编码更慢", None, True, ("-c:a", "flac", "-compression_level", "8")),
        QualityOption("fast", "快速压缩", "无损 · 编码最快", None, True, ("-c:a", "flac", "-compression_level", "2")),
    ),
)

WAV = OutputFormat(
    id="wav",
    label="WAV",
    extension="wav",
    description="未压缩 PCM，编辑和归档友好",
    default_quality="pcm16",
    lossless=True,
    qualities=(
        QualityOption("pcm16", "16-bit PCM", "CD 级 · 兼容性最好", None, True, ("-c:a", "pcm_s16le")),
        QualityOption("pcm24", "24-bit PCM", "高精度 · 体积更大", None, True, ("-c:a", "pcm_s24le")),
    ),
)

M4A = OutputFormat(
    id="m4a",
    label="M4A",
    extension="m4a",
    description="AAC-LC，手机和 Apple 设备友好",
    default_quality="256",
    qualities=(
        QualityOption("256", "256 kbps", "AAC · 高品质", 256, False, ("-c:a", "aac", "-b:a", "256k")),
        QualityOption("192", "192 kbps", "AAC · 均衡", 192, False, ("-c:a", "aac", "-b:a", "192k")),
        QualityOption("128", "128 kbps", "AAC · 省空间", 128, False, ("-c:a", "aac", "-b:a", "128k")),
    ),
)

OGG = OutputFormat(
    id="ogg",
    label="OGG",
    extension="ogg",
    description="Vorbis 编码，开源播放器友好",
    default_quality="q6",
    qualities=(
        QualityOption("q8", "极高 · Q8", "约 256 kbps", 256, False, ("-c:a", "libvorbis", "-q:a", "8")),
        QualityOption("q6", "高 · Q6", "约 192 kbps", 192, False, ("-c:a", "libvorbis", "-q:a", "6")),
        QualityOption("q4", "标准 · Q4", "约 128 kbps", 128, False, ("-c:a", "libvorbis", "-q:a", "4")),
    ),
)

OUTPUT_FORMATS: tuple[OutputFormat, ...] = (MP3, FLAC, WAV, M4A, OGG)
FORMAT_BY_ID = {fmt.id: fmt for fmt in OUTPUT_FORMATS}
DEFAULT_FORMAT = "mp3"

EXTENSION_TO_FORMAT = {
    ".mp3": "mp3",
    ".flac": "flac",
    ".wav": "wav",
    ".m4a": "m4a",
    ".aac": "m4a",
    ".ogg": "ogg",
    ".oga": "ogg",
}


def format_by_id(format_id: str | None) -> OutputFormat:
    return FORMAT_BY_ID.get((format_id or "").lower(), FORMAT_BY_ID[DEFAULT_FORMAT])


def format_for_extension(extension: str) -> OutputFormat | None:
    key = extension.lower()
    if not key.startswith("."):
        key = "." + key
    format_id = EXTENSION_TO_FORMAT.get(key)
    return FORMAT_BY_ID.get(format_id) if format_id else None


def quality_for(format_id: str, quality_id: str | None) -> QualityOption:
    return format_by_id(format_id).quality(quality_id)
