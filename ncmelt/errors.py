"""Shared error types for the NCM converter."""

from __future__ import annotations


class ConverterError(Exception):
    """Base class for errors that can be shown to the user."""

    default_message = "转换失败"

    @property
    def user_message(self) -> str:
        message = str(self).strip()
        return message or self.default_message


class NCMError(ConverterError):
    default_message = "NCM 文件无法读取"


class NCMFormatError(NCMError):
    default_message = "不是有效的 NCM 文件"


class NCMTruncatedError(NCMError):
    default_message = "NCM 文件不完整或已损坏"


class FFmpegNotFoundError(ConverterError):
    default_message = "找不到 FFmpeg 编码器"


class FFmpegError(ConverterError):
    default_message = "音频转码失败"


class OutputError(ConverterError):
    default_message = "无法写入输出文件"


class ConversionCancelled(ConverterError):
    default_message = "已取消转换"
