"""Command line interface for ncmelt."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import APP_SUBTITLE, __version__
from .converter import convert_ncm
from .errors import ConverterError
from .formats import (
    DEFAULT_FORMAT,
    OUTPUT_FORMATS,
    OutputFormat,
    format_by_id,
    format_for_extension,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ncmelt",
        description=f"ncmelt - {APP_SUBTITLE}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  ncmelt input.ncm -o output.mp3\n"
            "  ncmelt input.ncm -o output.flac\n"
            "  ncmelt a.ncm b.ncm -o D:\\Music --format flac --quality max\n"
        ),
    )
    parser.add_argument("inputs", nargs="+", help="一个或多个 .ncm 文件")
    parser.add_argument(
        "-o",
        "--output",
        help="输出文件（单个输入）或输出目录（批量）",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=[fmt.id for fmt in OUTPUT_FORMATS],
        help="输出格式；有 -o 扩展名时自动判断",
    )
    parser.add_argument(
        "-q",
        "--quality",
        help="音质档位：mp3 320/256/192/128/v0；flac standard/max/fast；"
        "wav pcm16/pcm24；m4a 256/192/128；ogg q8/q6/q4",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="允许覆盖已存在的输出文件"
    )
    parser.add_argument(
        "--no-tags", action="store_true", help="不写入歌曲名/歌手/专辑标签"
    )
    parser.add_argument("--no-cover", action="store_true", help="不嵌入封面图片")
    parser.add_argument(
        "--name-style",
        choices=["artist-title", "title"],
        default="artist-title",
        help="文件名样式：歌手 - 歌名（默认）或仅歌名",
    )
    parser.add_argument("--quiet", action="store_true", help="不显示进度")
    parser.add_argument(
        "--version", action="version", version=f"ncmelt {__version__}"
    )
    return parser


def _resolve_format(args, inputs: list[Path], output: Path | None):
    inferred = None
    if output is not None and not _looks_like_directory(output, len(inputs)):
        inferred = format_for_extension(output.suffix)
        if inferred is None:
            raise ValueError(
                f"无法从输出扩展名“{output.suffix or '无'}”判断格式；"
                "请指定 --format 或使用 .mp3/.flac/.wav/.m4a/.ogg。"
            )
    requested = format_by_id(args.format) if args.format else None
    if inferred and requested and inferred.id != requested.id:
        raise ValueError(
            f"输出扩展名对应 {inferred.label}，但 --format 指定了 {requested.label}"
        )
    return inferred or requested or format_by_id(DEFAULT_FORMAT)


def _looks_like_directory(path: Path, input_count: int) -> bool:
    if path.is_dir():
        return True
    if path.exists():
        return False
    # A path that already names a supported output format is a file. This
    # keeps `-o mix.mp3` from silently becoming a directory in batch mode.
    if format_for_extension(path.suffix) is not None:
        return False
    if input_count > 1:
        return True
    return not path.suffix


def _validate_quality(fmt: OutputFormat, quality_id: str | None) -> str:
    if not quality_id:
        return fmt.default_quality
    valid = {q.id: q for q in fmt.qualities}
    if quality_id not in valid:
        choices = " / ".join(valid)
        raise ValueError(f"{fmt.label} 不支持音质“{quality_id}”，可选：{choices}")
    return quality_id


def _print_formats() -> None:
    for fmt in OUTPUT_FORMATS:
        qualities = "、".join(f"{q.id}={q.label}" for q in fmt.qualities)
        print(f"{fmt.id:4} {fmt.extension:4} {fmt.description}")
        print(f"     音质：{qualities}")


def _configure_console() -> None:
    """Keep Chinese paths readable in the Windows console."""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    parser = _build_parser()
    args = parser.parse_args(argv)
    inputs = [Path(value).expanduser() for value in args.inputs]
    missing = [path for path in inputs if not path.is_file()]
    if missing:
        for path in missing:
            print(f"错误：找不到输入文件：{path}", file=sys.stderr)
        return 1
    try:
        output = Path(args.output).expanduser() if args.output else None
        if (
            output is not None
            and len(inputs) > 1
            and not _looks_like_directory(output, len(inputs))
        ):
            print(
                "错误：多个输入文件时，-o 必须是输出目录，不能是文件路径",
                file=sys.stderr,
            )
            return 2
        fmt = _resolve_format(args, inputs, output)
        quality_id = _validate_quality(fmt, args.quality)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    if output is not None:
        is_dir = _looks_like_directory(output, len(inputs))
        if not is_dir and len(inputs) > 1:
            print("错误：多个输入文件时，-o 必须是输出目录", file=sys.stderr)
            return 2
        if is_dir:
            output_dir = output
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                print(f"错误：无法创建输出目录：{exc}", file=sys.stderr)
                return 1
            destinations = [None] * len(inputs)
        else:
            destinations = [output]
            output_dir = output.parent
    else:
        output_dir = None
        destinations = [None] * len(inputs)

    total = len(inputs)
    failures = 0
    for index, (source, destination) in enumerate(zip(inputs, destinations), start=1):
        label = f"[{index}/{total}] {source.name}"
        if not args.quiet:
            print(label, flush=True)
        last_percent = -1

        def progress(fraction: float) -> None:
            nonlocal last_percent
            if args.quiet or not sys.stderr.isatty():
                return
            percent = int(max(0.0, min(1.0, fraction)) * 100)
            if percent >= last_percent + 5 or percent == 100:
                last_percent = percent
                print(f"\r  转换中 {percent:3d}%", end="", file=sys.stderr, flush=True)

        try:
            outcome = convert_ncm(
                source,
                output_dir,
                fmt.id,
                quality_id,
                destination=destination,
                overwrite=args.overwrite,
                overwrite_existing=args.overwrite,
                naming=args.name_style,
                write_tags=not args.no_tags,
                embed_cover=not args.no_cover,
                on_progress=progress,
            )
        except ConverterError as exc:
            failures += 1
            print(f"  失败：{exc.user_message}", file=sys.stderr)
            continue
        except KeyboardInterrupt:
            print("\n已取消", file=sys.stderr)
            return 130
        except Exception as exc:
            failures += 1
            print(f"  失败：{exc}", file=sys.stderr)
            continue
        if not args.quiet:
            if sys.stderr.isatty():
                print("\r", end="", file=sys.stderr)
            size_mb = outcome.output.stat().st_size / 1024 / 1024
            print(
                f"  完成：{outcome.output}  ({outcome.output_format.label}, "
                f"{size_mb:.1f} MB)"
            )
        else:
            print(outcome.output)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
