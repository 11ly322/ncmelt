"""Reusable UI pieces for the ncmelt interface."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image

from . import theme as T
from .formats import format_by_id
from .ncm import NCMHeader


def asset_path(name: str) -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / "assets" / name)
        candidates.append(Path(sys._MEIPASS) / "ncmelt" / "assets" / name)
    candidates.append(Path(__file__).resolve().parent / "assets" / name)
    candidates.append(Path(__file__).resolve().parent.parent / "assets" / name)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "assets" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def truncate(text: str, limit: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def tune_scrollable(frame: Any, scale: float) -> None:
    """Keep canvas scrolling pixel-aligned and avoid fractional repaints."""
    canvas = getattr(frame, "_parent_canvas", None)
    if canvas is None:
        return
    try:
        canvas.configure(yscrollincrement=max(1, int(round(scale))))
    except Exception:
        pass


class FastScrollbar(tk.Canvas):
    """Lightweight flat scrollbar for a CTkScrollableFrame."""

    def __init__(
        self,
        master,
        command,
        *,
        width: int,
        trough: str,
        thumb: str,
        hover: str,
    ):
        super().__init__(
            master,
            width=width,
            bg=trough,
            bd=0,
            highlightthickness=0,
            cursor="arrow",
        )
        self._command = command
        self._trough = trough
        self._thumb = thumb
        self._hover = hover
        self._first = 0.0
        self._last = 1.0
        self._drag_offset = 0
        self._active = False
        self.bind("<Configure>", self._draw, add="+")
        self.bind("<Button-1>", self._on_press, add="+")
        self.bind("<B1-Motion>", self._on_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Enter>", lambda _e: self._set_active(True), add="+")
        self.bind("<Leave>", lambda _e: self._set_active(False), add="+")
        self.bind("<MouseWheel>", self._on_wheel, add="+")

    def set(self, first, last) -> None:
        try:
            self._first = max(0.0, min(1.0, float(first)))
            self._last = max(0.0, min(1.0, float(last)))
        except (TypeError, ValueError):
            self._first, self._last = 0.0, 1.0
        self._draw()

    def _bounds(self) -> tuple[int, int]:
        height = max(1, self.winfo_height())
        pad = 2
        span = max(0, height - pad * 2)
        start = pad + self._first * span
        end = pad + self._last * span
        minimum = max(18, height // 12)
        if end - start < minimum:
            end = min(height - pad, start + minimum)
            start = max(pad, end - minimum)
        return int(start), int(max(start + 1, end))

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self.create_rectangle(0, 0, width, height, fill=self._trough, outline="")
        if self._last - self._first >= 0.999:
            return
        start, end = self._bounds()
        self.create_rectangle(
            3,
            start,
            max(4, width - 3),
            end,
            fill=self._hover if self._active else self._thumb,
            outline="",
        )

    def _set_active(self, active: bool) -> None:
        self._active = active
        self._draw()

    def _scroll_to(self, y: float) -> None:
        height = max(1, self.winfo_height())
        span = max(0.0, self._last - self._first)
        fraction = max(0.0, min(1.0, (y - self._drag_offset) / height))
        value = max(0.0, min(1.0 - span, fraction - span / 2))
        self._command("moveto", value)

    def _on_press(self, event) -> None:
        start, end = self._bounds()
        if start <= event.y <= end:
            self._drag_offset = event.y - (start + end) // 2
        else:
            self._drag_offset = 0
        self._scroll_to(event.y)

    def _on_drag(self, event) -> None:
        self._scroll_to(event.y)

    def _on_release(self, _event) -> None:
        self._drag_offset = 0

    def _on_wheel(self, event) -> None:
        direction = -1 if event.delta > 0 else 1
        self._command("scroll", direction * 3, "units")


def install_fast_scrollbar(
    frame: Any,
    scale: float,
    *,
    trough: str,
    thumb: str,
    hover: str,
) -> None:
    """Replace CTk's shape-heavy scrollbar with a flat canvas bar."""
    canvas = getattr(frame, "_parent_canvas", None)
    old = getattr(frame, "_scrollbar", None)
    if canvas is None or old is None:
        return
    try:
        parent = old.master
        info = old.grid_info()
        old.destroy()
        bar = FastScrollbar(
            parent,
            canvas.yview,
            width=max(8, int(round(9 * scale))),
            trough=trough,
            thumb=thumb,
            hover=hover,
        )
        bar.grid(
            row=int(info.get("row", 1)),
            column=int(info.get("column", 1)),
            sticky="ns",
            padx=0,
            pady=0,
        )
        canvas.configure(yscrollcommand=bar.set)
        frame._scrollbar = bar
    except Exception:
        pass


def shrink_path(path: str, limit: int = 48) -> str:
    if len(path) <= limit:
        return path
    head = max(10, limit // 2 - 2)
    tail = max(12, limit - head - 1)
    return path[:head] + "…" + path[-tail:]


def human_size(size: int) -> str:
    if size >= 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024 / 1024:.1f} GB"
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def duration_text(seconds: float) -> str:
    if seconds <= 0:
        return "--:--"
    total = round(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def header_quality(header: NCMHeader) -> str:
    metadata = header.metadata
    if header.is_lossless:
        return "无损"
    if metadata and metadata.bitrate:
        return f"{round(metadata.bitrate / 1000)}k"
    return "音频"


def source_label(header: NCMHeader) -> str:
    return f"{header.format_label}  {header_quality(header)}"


@dataclass
class QueueItem:
    path: Path
    header: NCMHeader | None = None
    status: str = "ready"
    error: str = ""
    progress: float = 0.0
    output: Path | None = None
    media: Any = None

    @property
    def is_done(self) -> bool:
        return self.status == "done"

    @property
    def is_invalid(self) -> bool:
        return self.status == "invalid"

    @property
    def is_pending(self) -> bool:
        return self.status in ("ready", "failed", "cancelled")

    @property
    def title(self) -> str:
        if self.header and self.header.metadata:
            return self.header.metadata.display_title
        return self.path.stem

    @property
    def source_size(self) -> int:
        return self.header.file_size if self.header else self.path.stat().st_size

    @property
    def duration_seconds(self) -> float:
        if self.media is not None:
            return float(getattr(self.media, "duration_seconds", 0) or 0)
        if self.header and self.header.metadata:
            return self.header.metadata.duration_ms / 1000
        return 0.0

    @property
    def display_size(self) -> int:
        if self.output is not None and self.output.exists():
            return self.output.stat().st_size
        return self.source_size


class QueueRow(ctk.CTkFrame):
    """A dense table row with selection and per-file progress."""

    def __init__(self, master, item: QueueItem, app, index: int):
        super().__init__(
            master,
            fg_color=T.ROW if index % 2 == 0 else T.ROW_ALT,
            corner_radius=0,
            height=52,
        )
        self.item = item
        self.app = app
        self.index = index
        self._selected = False
        self._hover = False
        self.grid_propagate(False)
        app.configure_table_columns(self)
        self._build()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        for child in self.winfo_children():
            self._bind_select(child)
        self.refresh()
        app._register_drop_tree(self)

    def _bind_select(self, widget) -> None:
        try:
            widget.bind("<Button-1>", self._on_click, add="+")
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._bind_select(child)

    def _build(self) -> None:
        self.select_bar = ctk.CTkFrame(
            self, width=3, fg_color="transparent", corner_radius=0
        )
        self.select_bar.place(x=0, y=0, relheight=1)

        self.file_cell = ctk.CTkFrame(self, fg_color="transparent")
        self.file_cell.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=5)
        self.file_cell.grid_columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(
            self.file_cell,
            text="",
            anchor="w",
            height=20,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=12),
            text_color=T.TEXT,
        )
        self.title_label.grid(row=0, column=0, sticky="ew")
        self.sub_label = ctk.CTkLabel(
            self.file_cell,
            text="",
            anchor="w",
            height=16,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        )
        self.sub_label.grid(row=1, column=0, sticky="ew", pady=(1, 0))

        self.format_label = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
            text_color=T.TEXT_SOFT,
        )
        self.format_label.grid(row=0, column=1, sticky="w", padx=(0, 8))

        self.duration_label = ctk.CTkLabel(
            self,
            text="--:--",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_MONO, size=9),
            text_color=T.MUTED,
        )
        self.duration_label.grid(row=0, column=2, sticky="w", padx=(0, 8))

        self.size_label = ctk.CTkLabel(
            self,
            text="0 B",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_MONO, size=9),
            text_color=T.MUTED,
        )
        self.size_label.grid(row=0, column=3, sticky="w", padx=(0, 8))

        self.status_label = ctk.CTkLabel(
            self,
            text="待转换",
            anchor="e",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
            text_color=T.MUTED,
        )
        self.status_label.grid(row=0, column=4, sticky="e", padx=(0, 8))

        self.remove_btn = ctk.CTkButton(
            self,
            text="×",
            width=26,
            height=26,
            corner_radius=3,
            fg_color="transparent",
            hover_color=T.ROW_HOVER,
            text_color=T.SUBTLE,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=16),
            command=lambda: self.app.remove_item(self.item),
        )
        self.remove_btn.grid(row=0, column=5, sticky="e", padx=(0, 8))

        self.bottom_line = ctk.CTkFrame(self, height=1, fg_color=T.BORDER_SOFT)
        self.bottom_line.place(relx=0, rely=1, relwidth=1, anchor="sw")

    def _on_click(self, event) -> None:
        self.app.select_item(self.item, ctrl=bool(event.state & 0x0004))

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        if not self._selected:
            self.configure(fg_color=T.ROW_HOVER)

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        if not self._selected:
            self.configure(fg_color=T.ROW if self.index % 2 == 0 else T.ROW_ALT)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.select_bar.configure(fg_color=T.ACCENT if selected else "transparent")
        if selected:
            self.configure(fg_color=T.ROW_SELECTED)
        else:
            self.configure(fg_color=T.ROW_HOVER if self._hover else (
                T.ROW if self.index % 2 == 0 else T.ROW_ALT
            ))

    def set_index(self, index: int) -> None:
        self.index = index
        if not self._selected:
            self.configure(fg_color=T.ROW if index % 2 == 0 else T.ROW_ALT)

    def refresh(self) -> None:
        item = self.item
        self.title_label.configure(text=truncate(item.title, 50))
        invalid = item.status == "invalid"
        failed = item.status == "failed"
        if invalid or failed:
            self.sub_label.configure(
                text=truncate(item.error or item.path.name, 70), text_color=T.ERROR
            )
        elif item.status == "done" and item.media is not None:
            media = item.media
            self.sub_label.configure(
                text=f"{item.output.name if item.output else ''}  ·  已写入输出目录",
                text_color=T.SUBTLE,
            )
        else:
            self.sub_label.configure(text=truncate(item.path.name, 70), text_color=T.SUBTLE)

        if item.status == "done" and item.media is not None:
            media = item.media
            fmt = format_by_id(getattr(media, "format_id", "mp3"))
            self.format_label.configure(
                text=f"{fmt.label}  {'无损' if getattr(media, 'lossless', False) else str(getattr(media, 'bitrate_kbps', 0)) + 'k'}",
                text_color=T.SUCCESS,
            )
            self.duration_label.configure(text=duration_text(item.duration_seconds))
            self.size_label.configure(text=human_size(item.display_size))
        else:
            if item.header:
                self.format_label.configure(
                    text=source_label(item.header), text_color=T.TEXT_SOFT
                )
            else:
                self.format_label.configure(text="无法识别", text_color=T.ERROR)
            seconds = item.header.metadata.duration_ms / 1000 if item.header and item.header.metadata else 0
            self.duration_label.configure(text=duration_text(seconds))
            self.size_label.configure(
                text=human_size(item.source_size) if item.header else "—"
            )
        self._refresh_status()

    def _refresh_status(self) -> None:
        status = self.item.status
        if status == "ready":
            text, color = "待转换", T.MUTED
        elif status == "decrypt":
            text, color = f"解密 {round(self.item.progress * 100)}%", T.ACCENT
        elif status == "encode":
            text, color = f"转换 {round(self.item.progress * 100)}%", T.ACCENT
        elif status == "verify":
            text, color = "校验中", T.ACCENT
        elif status == "done":
            text, color = "完成", T.SUCCESS
        elif status == "failed":
            text, color = "失败", T.ERROR
        elif status == "cancelled":
            text, color = "已取消", T.WARNING
        elif status == "invalid":
            text, color = "无法识别", T.ERROR
        else:
            text, color = status, T.MUTED
        self.status_label.configure(text=text, text_color=color)


class SummaryBars(tk.Canvas):
    """A compact histogram-like format distribution block."""

    def __init__(self, master, app):
        super().__init__(
            master,
            width=1,
            height=app.px(34),
            bg=T.PANEL_DEEP,
            highlightthickness=0,
            bd=0,
        )
        self.app = app
        self.counts: dict[str, int] = {}
        self.bind("<Configure>", lambda _e: self.redraw())

    def set_counts(self, counts: dict[str, int]) -> None:
        self.counts = counts
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        baseline = height - self.app.px(6)
        entries = [(name, count) for name, count in self.counts.items() if count > 0]
        if not entries:
            self.create_line(
                self.app.px(6),
                baseline,
                width - self.app.px(6),
                baseline,
                fill=T.BORDER,
                width=max(1, self.app.px(1)),
            )
            return
        maximum = max(count for _, count in entries)
        slot = (width - self.app.px(12)) / len(entries)
        bar_w = min(self.app.px(44), slot * 0.52)
        for idx, (name, count) in enumerate(entries):
            cx = self.app.px(6) + slot * (idx + 0.5)
            bar_h = max(
                self.app.px(4),
                (baseline - self.app.px(4)) * (count / maximum),
            )
            color = {
                "MP3": T.ACCENT,
                "FLAC": "#8199C9",
                "AAC": "#63C8B5",
                "M4A": "#63C8B5",
                "OGG": T.ORANGE,
                "WAV": T.MUTED,
            }.get(name, T.STEEL)
            self.create_rectangle(
                cx - bar_w / 2,
                baseline - bar_h,
                cx + bar_w / 2,
                baseline,
                fill=color,
                outline="",
            )
            self.create_text(
                cx,
                baseline - bar_h - self.app.px(6),
                text=str(count),
                fill=T.TEXT_SOFT,
                font=(T.FONT_FAMILY, -max(8, self.app.px(8))),
            )


class EmptyState(ctk.CTkFrame):
    def __init__(self, master, on_add_files, on_add_folder):
        super().__init__(master, fg_color=T.BG, corner_radius=0)
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.place(relx=0.5, rely=0.46, anchor="center")

        icon_path = asset_path("app-128.png")
        if icon_path:
            image = Image.open(icon_path)
            self._icon = ctk.CTkImage(
                light_image=image, dark_image=image, size=(92, 92)
            )
            ctk.CTkLabel(inner, text="", image=self._icon).pack()
        ctk.CTkLabel(
            inner,
            text="拖入 NCM 文件开始",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=20, weight="bold"),
            text_color=T.TEXT,
        ).pack(pady=(16, 5))
        ctk.CTkLabel(
            inner,
            text="整个窗口都可以接收文件 · 支持批量解密与格式转换",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
            text_color=T.MUTED,
        ).pack()
        ctk.CTkLabel(
            inner,
            text="MP3   ·   FLAC   ·   WAV   ·   M4A   ·   OGG",
            font=ctk.CTkFont(family=T.FONT_MONO, size=9),
            text_color=T.SUBTLE,
        ).pack(pady=(12, 18))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack()
        ctk.CTkButton(
            row,
            text="添加文件",
            width=116,
            height=36,
            corner_radius=4,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11, weight="bold"),
            command=on_add_files,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="添加文件夹",
            width=116,
            height=36,
            corner_radius=4,
            fg_color="transparent",
            hover_color=T.ROW_HOVER,
            border_width=1,
            border_color=T.BORDER,
            text_color=T.TEXT_SOFT,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11),
            command=on_add_folder,
        ).pack(side="left")
        ctk.CTkLabel(
            inner,
            text="也可以按 Ctrl+O 选择文件",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        ).pack(pady=(14, 0))


class MenuPopup(ctk.CTkToplevel):
    """Small dark popup menu used by the toolbar."""

    @staticmethod
    def px(value: int, scale: float) -> int:
        return int(round(value * scale))

    def __init__(self, master, anchor, items, on_close=None):
        super().__init__(master)
        self._on_close = on_close
        self.withdraw()
        self.overrideredirect(True)
        self.configure(fg_color=T.BORDER)
        self.attributes("-topmost", True)
        self._items = items

        frame = ctk.CTkFrame(
            self,
            fg_color=T.PANEL,
            corner_radius=2,
            border_width=1,
            border_color=T.BORDER,
        )
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        self.frame = frame
        for item in items:
            if item is None:
                ctk.CTkFrame(frame, height=1, fg_color=T.BORDER).pack(
                    fill="x", padx=8, pady=3
                )
                continue
            label, command = item
            btn = ctk.CTkButton(
                frame,
                text=label,
                anchor="w",
                height=28,
                corner_radius=0,
                fg_color="transparent",
                hover_color=T.ROW_HOVER,
                text_color=T.TEXT_SOFT,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
                command=lambda c=command: self._choose(c),
            )
            btn.pack(fill="x", padx=2)

        self.update_idletasks()
        scale = max(1.0, master._get_window_scaling())
        # CTk multiplies geometry width/height by the window scale, while the
        # +x+y offsets are passed through as physical screen coordinates.
        width = max(214, round(frame.winfo_reqwidth() / scale))
        height = max(1, round(frame.winfo_reqheight() / scale)) + 2
        width_px, height_px = self.px(width, scale), self.px(height, scale)
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + self.px(1, scale)
        if x + width_px > self.winfo_screenwidth():
            x = max(0, self.winfo_screenwidth() - width_px - self.px(8, scale))
        if y + height_px > self.winfo_screenheight():
            y = max(0, anchor.winfo_rooty() - height_px - self.px(2, scale))
        self.geometry(f"{width}x{height}+{int(x)}+{int(y)}")
        self.deiconify()
        self.lift()
        self.update_idletasks()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<Button-1>", self._on_click, add="+")

    def _on_click(self, event) -> None:
        if event.x_root < self.winfo_rootx() or event.x_root > (
            self.winfo_rootx() + self.winfo_width()
        ):
            self.close()
            return
        if event.y_root < self.winfo_rooty() or event.y_root > (
            self.winfo_rooty() + self.winfo_height()
        ):
            self.close()

    def _choose(self, command) -> None:
        self.close()
        command()

    def close(self) -> None:
        if self.winfo_exists():
            try:
                self.grab_release()
            except Exception:
                pass
            if self._on_close is not None:
                self._on_close()
            self.destroy()
