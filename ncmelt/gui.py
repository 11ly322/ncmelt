"""Main window for ncmelt with workspace, side panel and status bar."""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import COPY, DND_FILES, TkinterDnD

from . import APP_NAME, APP_SUBTITLE
from . import __version__ as APP_VERSION
from . import theme as T
from .converter import convert_ncm, probe_source
from .errors import ConversionCancelled, ConverterError, FFmpegNotFoundError
from .formats import OUTPUT_FORMATS, format_by_id
from .settings import load_settings, log_path, save_settings
from .transcoder import ffmpeg_version, find_ffmpeg, open_in_explorer
from .ui_components import (
    EmptyState,
    QueueItem,
    QueueRow,
    asset_path,
    duration_text,
    human_size,
    truncate,
    tune_scrollable,
)
from .ui_menu import MenuPopup
from .ui_side import HelpDialog, SettingsDialog, SidePanel

LOG = logging.getLogger(__name__)


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


class ConverterApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        _enable_dpi_awareness()
        ctk.set_appearance_mode("dark")
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.scale = max(1.0, float(self._get_window_scaling()))
        self.settings = load_settings()
        self.format_id = self.settings.get("format", "mp3")
        if self.format_id not in {fmt.id for fmt in OUTPUT_FORMATS}:
            self.format_id = "mp3"
        self.quality_id = self._valid_quality(
            self.format_id, self.settings.get("qualities", {}).get(self.format_id)
        )
        self.output_mode = self.settings.get("output_mode", "source")
        if self.output_mode not in ("source", "custom"):
            self.output_mode = "source"
        self.output_dir = self.settings.get("output_dir", "")
        self.auto_open = bool(self.settings.get("auto_open"))
        self.naming = self.settings.get("naming", "artist-title")
        self.write_tags = bool(self.settings.get("write_tags", True))
        self.embed_cover = bool(self.settings.get("embed_cover", True))
        self.overwrite_existing = bool(self.settings.get("overwrite_existing"))
        self.panel_width = int(self.settings.get("panel_width", 350))
        self.panel_visible = bool(self.settings.get("panel_visible", True))

        self.items: list[QueueItem] = []
        self.rows: dict[Path, QueueRow] = {}
        self.selected: set[Path] = set()
        self.events: queue.Queue[dict] = queue.Queue()
        self.converting = False
        self.cancel_event: threading.Event | None = None
        self.worker: threading.Thread | None = None
        self.completed_dirs: list[Path] = []
        self.batch_total = 0
        self.batch_started = 0.0
        self.current_index = 0
        self._closing = False
        self._close_deadline = 0.0
        self._dnd_registered: set[str] = set()
        self._drag_hide_job: str | None = None
        self._last_drop = (0.0, "")
        self._scroll_paint_job: str | None = None
        self._settings_dialog: SettingsDialog | None = None
        self._help_dialog: HelpDialog | None = None

        self.title(f"{APP_NAME} {APP_VERSION} — {APP_SUBTITLE}")
        self.configure(fg_color=T.BG)
        self.minsize(1080, 680)
        self._set_window_geometry()
        icon = asset_path("app.ico")
        if icon:
            try:
                self.iconbitmap(str(icon))
            except Exception:
                LOG.debug("Could not set window icon", exc_info=True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_topbar()
        self._build_content()
        self._build_statusbar()
        self._build_menus()
        self._bind_shortcuts()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain_events)
        self.after(250, self._check_ffmpeg)
        self.after(220, self._register_drop_tree)
        self._refresh_queue_ui()
        self._sync_panel_button()
        self._update_start_buttons()

    # ------------------------------------------------------------------
    # Helpers / window
    # ------------------------------------------------------------------
    def px(self, value: int) -> int:
        return int(round(value * self.scale))

    def asset_icon(self, name: str) -> str | None:
        path = asset_path(name)
        return str(path) if path else None

    def _set_window_geometry(self) -> None:
        self.update_idletasks()
        scale = self.scale
        logical_w = self.winfo_screenwidth() / scale
        logical_h = self.winfo_screenheight() / scale
        width = min(1280, max(1080, int(logical_w) - 80))
        height = min(800, max(680, int(logical_h) - 100))
        x = max(8, (int(logical_w) - width) // 2)
        y = max(8, (int(logical_h) - height) // 2 - 10)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=T.TOOLBAR, corner_radius=0, height=38)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        menu_strip = ctk.CTkFrame(bar, fg_color="transparent")
        menu_strip.grid(
            row=0, column=0, sticky="w", padx=(self.px(6), 0), pady=self.px(4)
        )
        self._menu_buttons: dict[str, ctk.CTkButton] = {}
        for key, label in (
            ("file", "文件"),
            ("edit", "编辑"),
            ("view", "视图"),
            ("tools", "工具"),
            ("help", "帮助"),
        ):
            btn = ctk.CTkButton(
                menu_strip,
                text=label,
                width=52,
                height=28,
                corner_radius=2,
                fg_color="transparent",
                hover_color=T.ROW_HOVER,
                text_color=T.TEXT_SOFT,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
                command=lambda k=key: self._popup_menu(k),
            )
            btn.pack(side="left", padx=(0, 1))
            self._menu_buttons[key] = btn

        quick = ctk.CTkFrame(bar, fg_color="transparent")
        quick.grid(
            row=0, column=1, sticky="w", padx=(self.px(12), 0), pady=self.px(4)
        )
        self.add_btn = self._tool_button(quick, "＋ 文件", self.choose_files)
        self.add_folder_btn = self._tool_button(quick, "文件夹", self.choose_folder)
        self.remove_btn = self._tool_button(quick, "移除", self.remove_selected)
        self.clear_btn = self._tool_button(quick, "清空", self.clear_all)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(
            row=0, column=2, sticky="e", padx=(0, self.px(8)), pady=self.px(4)
        )
        self.panel_btn = self._tool_button(right, "面板", self.toggle_panel)
        self.settings_btn = self._tool_button(right, "设置", self.show_settings)
        self.top_start_btn = ctk.CTkButton(
            right,
            text="开始转换",
            width=96,
            height=29,
            corner_radius=3,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10, weight="bold"),
            command=self.toggle_conversion,
        )
        self.top_start_btn.pack(side="left", padx=(self.px(8), 0))

        ctk.CTkFrame(self, height=1, fg_color=T.BORDER).grid(
            row=0, column=0, sticky="sew"
        )

    def _tool_button(self, parent, text: str, command) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            parent,
            text=text,
            width=64,
            height=29,
            corner_radius=2,
            fg_color="transparent",
            hover_color=T.ROW_HOVER,
            text_color=T.TEXT_SOFT,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
            command=command,
        )
        btn.pack(side="left", padx=(0, 2))
        return btn

    def _build_content(self) -> None:
        content = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, minsize=self.px(4))
        content.grid_columnconfigure(2, minsize=self.px(self.panel_width))
        self.content_frame = content

        workspace = ctk.CTkFrame(content, fg_color=T.BG, corner_radius=0)
        workspace.grid(row=0, column=0, sticky="nsew")
        workspace.grid_rowconfigure(1, weight=1)
        workspace.grid_columnconfigure(0, weight=1)
        self.workspace = workspace

        self.table_header = ctk.CTkFrame(
            workspace, fg_color=T.TOOLBAR, corner_radius=0, height=32
        )
        self.table_header.grid(row=0, column=0, sticky="ew")
        self.table_header.grid_propagate(False)
        self.configure_table_columns(self.table_header)
        headers = ("文件", "格式", "时长", "大小", "状态")
        for col, text in enumerate(headers):
            ctk.CTkLabel(
                self.table_header,
                text=text,
                anchor="e" if col == 4 else "w",
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
                text_color=T.SUBTLE,
            ).grid(
                row=0,
                column=col,
                sticky="ew",
                padx=(self.px(14) if col == 0 else 0, self.px(8)),
                pady=self.px(6),
            )
        ctk.CTkLabel(self.table_header, text="", width=26).grid(
            row=0, column=5, sticky="e", padx=(0, self.px(8))
        )
        ctk.CTkFrame(workspace, height=1, fg_color=T.BORDER).grid(
            row=0, column=0, sticky="sew"
        )

        self.file_list = ctk.CTkScrollableFrame(
            workspace,
            fg_color=T.BG,
            corner_radius=0,
            scrollbar_button_color=T.BORDER,
            scrollbar_button_hover_color=T.SUBTLE,
            scrollbar_fg_color="transparent",
        )
        self.file_list.grid(row=1, column=0, sticky="nsew")
        self.file_list.grid_columnconfigure(0, weight=1)
        tune_scrollable(self.file_list, self.scale)

        self.empty_state = EmptyState(
            workspace, self.choose_files, self.choose_folder
        )
        self.empty_state.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.empty_state.lift()

        divider = ctk.CTkFrame(
            content,
            fg_color=T.BORDER,
            width=self.px(1),
            corner_radius=0,
            cursor="sb_h_double_arrow",
        )
        divider.grid(row=0, column=1, sticky="ns")
        divider.bind("<ButtonPress-1>", self._panel_drag_start)
        divider.bind("<B1-Motion>", self._panel_drag_move)
        divider.bind("<ButtonRelease-1>", self._panel_drag_end)
        self.divider = divider

        self.side_panel = SidePanel(content, self)
        self.side_panel.grid(row=0, column=2, sticky="nsew")
        self._apply_panel_visibility()

    def configure_table_columns(self, widget) -> None:
        widget.grid_columnconfigure(0, weight=1, minsize=self.px(260))
        widget.grid_columnconfigure(1, minsize=self.px(145))
        widget.grid_columnconfigure(2, minsize=self.px(58))
        widget.grid_columnconfigure(3, minsize=self.px(76))
        widget.grid_columnconfigure(4, minsize=self.px(86))
        widget.grid_columnconfigure(5, minsize=self.px(30))

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=T.TOOLBAR, corner_radius=0, height=30)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkFrame(bar, height=1, fg_color=T.BORDER).grid(
            row=0, column=0, columnspan=3, sticky="ew"
        )
        self.status_label = ctk.CTkLabel(
            bar,
            text="●  就绪",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.MUTED,
        )
        self.status_label.grid(
            row=1, column=0, sticky="w", padx=(self.px(10), 0), pady=(self.px(4), 0)
        )
        self.queue_info = ctk.CTkLabel(
            bar,
            text="0 个文件 · 总时长 00:00 · 0 B",
            anchor="center",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        )
        self.queue_info.grid(row=1, column=1, sticky="ew", pady=(self.px(4), 0))
        ctk.CTkLabel(
            bar,
            text="Ctrl+O 添加   Ctrl+Enter 转换   Del 移除   F1 帮助",
            anchor="e",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        ).grid(
            row=1,
            column=2,
            sticky="e",
            padx=(0, self.px(10)),
            pady=(self.px(4), 0),
        )

    # ------------------------------------------------------------------
    # Menus & shortcuts
    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        self._menu_specs: dict[str, list] = {
            "file": [
                ("添加文件…        Ctrl+O", self.choose_files),
                ("添加文件夹…      Ctrl+Shift+O", self.choose_folder),
                None,
                ("打开输出目录", self.open_outputs),
                None,
                ("退出", self._on_close),
            ],
            "edit": [
                ("移除选中        Delete", self.remove_selected),
                ("全选            Ctrl+A", self.select_all),
                ("清空列表        Ctrl+L", self.clear_all),
            ],
            "view": [
                ("显示 / 隐藏转换面板   Ctrl+B", self.toggle_panel),
                ("重置窗口大小", self._reset_window),
            ],
            "tools": [
                ("开始转换        Ctrl+Enter", self.toggle_conversion),
                None,
                ("打开日志目录", self.open_logs),
            ],
            "help": [
                ("使用说明        F1", self.show_help),
                ("GitHub 项目页", self.open_github),
                ("关于 ncmelt", self.show_help),
            ],
        }
        self._menu_popup = None

    def _popup_menu(self, key: str) -> None:
        if self._menu_popup is not None and self._menu_popup.winfo_exists():
            self._menu_popup.close()
        button = self._menu_buttons[key]
        self._menu_popup = MenuPopup(
            self,
            button,
            self._menu_specs[key],
            on_close=lambda: setattr(self, "_menu_popup", None),
        )

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-o>", lambda _e: self.choose_files())
        self.bind_all("<Control-O>", lambda _e: self.choose_files())
        self.bind_all("<Control-Shift-O>", lambda _e: self.choose_folder())
        self.bind_all("<Control-Shift-o>", lambda _e: self.choose_folder())
        self.bind_all("<Control-Return>", lambda _e: self.toggle_conversion())
        self.bind_all("<Control-a>", lambda _e: self.select_all())
        self.bind_all("<Control-A>", lambda _e: self.select_all())
        self.bind_all("<Control-l>", lambda _e: self.clear_all())
        self.bind_all("<Control-L>", lambda _e: self.clear_all())
        self.bind_all("<Control-b>", lambda _e: self.toggle_panel())
        self.bind_all("<Control-B>", lambda _e: self.toggle_panel())
        self.bind_all("<Delete>", lambda _e: self.remove_selected())
        self.bind_all("<F1>", lambda _e: self.show_help())
        self.bind_all("<Escape>", self._escape)
        self.bind_all("<MouseWheel>", self._queue_scroll_paint, add="+")

    def _escape(self, event=None) -> None:
        # A dialog's own Escape binding runs before this global binding. Do not
        # let closing a dialog also cancel the batch conversion underneath it.
        widget = getattr(event, "widget", None)
        if widget is not None:
            try:
                if widget.winfo_toplevel() is not self:
                    return
            except Exception:
                return
        if (
            self._settings_dialog is not None
            and self._settings_dialog.winfo_exists()
        ) or (self._help_dialog is not None and self._help_dialog.winfo_exists()):
            return
        if self.converting:
            self._request_cancel()
        elif self.selected:
            self.selected.clear()
            self._refresh_selection_styles()

    # ------------------------------------------------------------------
    # Queue import
    # ------------------------------------------------------------------
    def choose_files(self) -> None:
        if self.converting:
            return
        paths = filedialog.askopenfilenames(
            parent=self,
            title="添加 NCM 文件",
            initialdir=self._initial_dir(),
            filetypes=[("网易云 NCM 文件", "*.ncm"), ("所有文件", "*.*")],
        )
        if paths:
            self.add_paths(list(paths))

    def choose_folder(self) -> None:
        if self.converting:
            return
        folder = filedialog.askdirectory(
            parent=self, title="添加包含 NCM 的文件夹", initialdir=self._initial_dir()
        )
        if folder:
            self.add_paths([folder])

    def _initial_dir(self) -> str:
        last = self.settings.get("last_dir", "")
        if last and Path(last).is_dir():
            return str(last)
        music = Path.home() / "Music"
        return str(music) if music.is_dir() else str(Path.home())

    def add_paths(self, raw_paths) -> None:
        if self.converting:
            self._set_status("转换进行中，暂时不能添加文件", T.WARNING)
            return
        files, ignored, duplicates = self._collect_inputs(list(raw_paths))
        if not files:
            if ignored:
                messagebox.showinfo(
                    "没有 NCM 文件",
                    "没有找到新的 .ncm 文件。\n支持直接拖入文件或包含 NCM 的文件夹。",
                    parent=self,
                )
            self._set_status("没有找到新的 NCM 文件", T.MUTED)
            return
        self._set_status(f"正在读取 {len(files)} 个文件…", T.MUTED)
        self.update_idletasks()
        invalid = 0
        for path in files:
            item = QueueItem(path=path)
            try:
                item.header = probe_source(path)
            except ConverterError as exc:
                item.status = "invalid"
                item.error = exc.user_message
                invalid += 1
            except Exception as exc:
                LOG.exception("Probe failed: %s", path)
                item.status = "invalid"
                item.error = f"读取失败：{exc}"
                invalid += 1
            self.items.append(item)
            row = QueueRow(self.file_list, item, self, len(self.items) - 1)
            row.pack(fill="x", padx=0, pady=(0, 1))
            self.rows[path] = row
        self.settings["last_dir"] = str(files[0].parent)
        self._save_settings()
        self._refresh_queue_ui()
        self._register_drop_tree(self)
        msg = f"已添加 {len(files) - invalid} 个文件"
        if invalid:
            msg += f"，{invalid} 个无法识别"
        if duplicates:
            msg += f"，跳过 {duplicates} 个重复项"
        if ignored:
            msg += f"，忽略 {ignored} 个非 NCM 文件"
        self._set_status(msg, T.WARNING if invalid else T.SUCCESS)

    def _collect_inputs(self, raw_paths):
        files: list[Path] = []
        ignored = 0
        duplicates = 0
        seen: set[str] = set()
        existing = {os.path.normcase(str(item.path)) for item in self.items}

        def consider(path: Path) -> None:
            nonlocal ignored, duplicates
            if not path.is_file() or path.suffix.lower() != ".ncm":
                ignored += 1
                return
            key = os.path.normcase(str(path))
            if key in seen or key in existing:
                duplicates += 1
                return
            seen.add(key)
            files.append(path)

        for raw in raw_paths:
            try:
                path = Path(raw).expanduser()
                if not path.is_absolute():
                    path = Path.cwd() / path
                path = Path(os.path.abspath(path))
            except (OSError, ValueError):
                ignored += 1
                continue
            if path.is_dir():
                for root, dirs, names in os.walk(path):
                    dirs.sort(key=str.casefold)
                    names.sort(key=str.casefold)
                    for name in names:
                        if name.lower().endswith(".ncm"):
                            consider(Path(root) / name)
            else:
                consider(path)
        return files, ignored, duplicates

    def _refresh_queue_ui(self) -> None:
        count = len(self.items)
        done = sum(1 for item in self.items if item.is_done)
        invalid = sum(1 for item in self.items if item.is_invalid)
        seconds = sum(item.duration_seconds for item in self.items)
        size = sum(item.source_size for item in self.items)
        counts: dict[str, int] = {}
        for item in self.items:
            if item.header:
                label = item.header.format_label
                counts[label] = counts.get(label, 0) + 1
        if count:
            self.empty_state.place_forget()
            self.table_header.grid()
            self.file_list.grid()
        else:
            self.table_header.grid_remove()
            self.file_list.grid_remove()
            self.empty_state.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.empty_state.lift()
        self.queue_info.configure(
            text=f"{count} 个文件 · 总时长 {duration_text(seconds)} · {human_size(size)}"
        )
        self.side_panel.set_stats(count, done, invalid, seconds, size, counts)
        self.side_panel._refresh_output_warning()
        self._update_start_buttons()
        self._update_toolbar_states()

    def _update_toolbar_states(self) -> None:
        state = "disabled" if self.converting or not self.items else "normal"
        self.remove_btn.configure(state=state)
        self.clear_btn.configure(state=state)
        self.add_btn.configure(state="disabled" if self.converting else "normal")
        self.add_folder_btn.configure(
            state="disabled" if self.converting else "normal"
        )

    def _update_start_buttons(self) -> None:
        if self.converting:
            for button in (self.top_start_btn, self.side_panel.start_btn):
                button.configure(
                    text="取消转换",
                    fg_color=T.ERROR_SOFT,
                    hover_color="#452028",
                    border_width=1,
                    border_color="#7A3038",
                    text_color="#FF9CA6",
                    state="normal",
                )
            return
        pending = [item for item in self.items if item.is_pending]
        done = [item for item in self.items if item.is_done]
        if not self.items or (not pending and not done):
            text, state = "开始转换", "disabled"
        elif pending:
            text, state = "开始转换", "normal"
        else:
            text, state = "重新转换", "normal"
        for button in (self.top_start_btn, self.side_panel.start_btn):
            button.configure(
                text=text,
                state="normal",
                fg_color=T.ACCENT if state == "normal" else T.PANEL_ALT,
                hover_color=T.ACCENT_HOVER if state == "normal" else T.PANEL_ALT,
                border_width=0,
                text_color="#FFFFFF" if state == "normal" else T.SUBTLE,
            )
            button.configure(state=state)

    # ------------------------------------------------------------------
    # Selection / removal
    # ------------------------------------------------------------------
    def select_item(self, item: QueueItem, ctrl: bool = False) -> None:
        if ctrl:
            if item.path in self.selected:
                self.selected.remove(item.path)
            else:
                self.selected.add(item.path)
        else:
            self.selected = {item.path}
        self._refresh_selection_styles()

    def select_all(self) -> None:
        if self.converting:
            return
        self.selected = {item.path for item in self.items if not item.is_invalid}
        self._refresh_selection_styles()

    def _refresh_selection_styles(self) -> None:
        for path, row in self.rows.items():
            row.set_selected(path in self.selected)
        self._update_toolbar_states()

    def remove_item(self, item: QueueItem) -> None:
        if self.converting:
            return
        row = self.rows.pop(item.path, None)
        if row is not None:
            row.destroy()
        try:
            self.items.remove(item)
        except ValueError:
            return
        self.selected.discard(item.path)
        self._reindex_rows()
        self._refresh_queue_ui()
        self._set_status(f"已移除 {item.path.name}", T.MUTED)

    def remove_selected(self) -> None:
        if self.converting or not self.selected:
            return
        count = len(self.selected)
        for item in list(self.items):
            if item.path in self.selected:
                row = self.rows.pop(item.path, None)
                if row is not None:
                    row.destroy()
                self.items.remove(item)
        self.selected.clear()
        self._reindex_rows()
        self._refresh_queue_ui()
        self._set_status(f"已移除 {count} 个文件", T.MUTED)

    def clear_all(self) -> None:
        if self.converting or not self.items:
            return
        count = len(self.items)
        for row in self.rows.values():
            row.destroy()
        self.rows.clear()
        self.items.clear()
        self.selected.clear()
        self.completed_dirs.clear()
        self.side_panel.set_open_enabled(False)
        self.side_panel.reset_progress()
        self._refresh_queue_ui()
        self._set_status(f"已清空 {count} 个文件", T.MUTED)

    def _reindex_rows(self) -> None:
        for idx, item in enumerate(self.items):
            row = self.rows.get(item.path)
            if row is not None:
                row.set_index(idx)

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------
    def _valid_quality(self, format_id: str, quality_id: str | None) -> str:
        fmt = format_by_id(format_id)
        if any(q.id == quality_id for q in fmt.qualities):
            return quality_id  # type: ignore[return-value]
        return fmt.default_quality

    def set_format(self, format_id: str) -> None:
        if self.converting or self.format_id == format_id:
            return
        self.format_id = format_by_id(format_id).id
        saved = self.settings.setdefault("qualities", {})
        self.quality_id = self._valid_quality(
            self.format_id, saved.get(self.format_id)
        )
        self.settings["format"] = self.format_id
        saved[self.format_id] = self.quality_id
        self.side_panel.refresh_format()
        self._save_settings()
        self._register_drop_tree(self.side_panel)
        self._set_status(
            f"输出格式：{format_by_id(self.format_id).label}", T.MUTED
        )

    def set_quality(self, quality_id: str) -> None:
        if self.converting:
            return
        self.quality_id = self._valid_quality(self.format_id, quality_id)
        self.settings.setdefault("qualities", {})[
            self.format_id
        ] = self.quality_id
        self.side_panel.refresh_format()
        self._save_settings()

    def choose_output_dir(self) -> None:
        if self.converting:
            return
        initial = (
            self.output_dir if self.output_mode == "custom" else self._initial_dir()
        )
        if not Path(initial).is_dir():
            initial = self._initial_dir()
        folder = filedialog.askdirectory(
            parent=self, title="选择输出目录", initialdir=initial
        )
        if folder:
            self.output_dir = folder
            self.output_mode = "custom"
            self.settings["output_mode"] = "custom"
            self.settings["output_dir"] = folder
            self.side_panel.set_output_display()
            self._save_settings()
            self._set_status(f"输出目录：{folder}", T.MUTED)

    def set_output_mode(self, mode: str) -> None:
        if self.converting:
            return
        if mode == "custom" and not self.output_dir:
            self.choose_output_dir()
            return
        self.output_mode = "custom" if mode == "custom" else "source"
        self.settings["output_mode"] = self.output_mode
        self.side_panel.set_output_display()
        self._save_settings()

    def set_bool_setting(self, key: str, value: bool) -> None:
        if self.converting:
            return
        if key == "write_tags":
            self.write_tags = bool(value)
        elif key == "embed_cover":
            self.embed_cover = bool(value)
        elif key == "auto_open":
            self.auto_open = bool(value)
        self.settings[key] = bool(value)
        self.side_panel.refresh_switches()
        self._save_settings()

    def set_naming(self, naming: str) -> None:
        if self.converting:
            return
        self.naming = "title" if naming == "title" else "artist-title"
        self.settings["naming"] = self.naming
        self.side_panel.refresh_switches()
        self._save_settings()

    def set_overwrite(self, value: bool) -> None:
        if self.converting:
            return
        self.overwrite_existing = bool(value)
        self.settings["overwrite_existing"] = self.overwrite_existing
        self.side_panel.refresh_switches()
        self._save_settings()

    def reset_page_options(self) -> None:
        if self.converting:
            return
        self.auto_open = False
        self.overwrite_existing = False
        self.settings.update(
            {
                "auto_open": False,
                "overwrite_existing": False,
            }
        )
        self.side_panel.refresh_switches()
        self._save_settings()
        self._set_status("已恢复本页默认值", T.MUTED)

    # ------------------------------------------------------------------
    # Panel / dialogs
    # ------------------------------------------------------------------
    def _sync_panel_button(self) -> None:
        if self.panel_visible:
            self.panel_btn.configure(fg_color=T.ACCENT_SOFT, text_color=T.ACCENT)
        else:
            self.panel_btn.configure(fg_color="transparent", text_color=T.TEXT_SOFT)

    def _apply_panel_visibility(self) -> None:
        if self.panel_visible:
            self.content_frame.grid_columnconfigure(1, minsize=self.px(4))
            self.content_frame.grid_columnconfigure(
                2, minsize=self.px(self.panel_width)
            )
            self.side_panel.grid()
            self.divider.grid()
        else:
            # grid_remove() hides the widgets but a column minsize would keep
            # reserving their width, leaving a blank strip on the right.
            self.content_frame.grid_columnconfigure(1, minsize=0)
            self.content_frame.grid_columnconfigure(2, minsize=0)
            self.side_panel.grid_remove()
            self.divider.grid_remove()

    def toggle_panel(self) -> None:
        self.panel_visible = not self.panel_visible
        self.settings["panel_visible"] = self.panel_visible
        self._apply_panel_visibility()
        self._sync_panel_button()
        self._save_settings()

    def _panel_drag_start(self, event) -> None:
        self._drag_start_x = event.x_root
        self._drag_start_width = self.panel_width

    def _panel_drag_move(self, event) -> None:
        if not hasattr(self, "_drag_start_x"):
            return
        delta = (event.x_root - self._drag_start_x) / self.scale
        width = int(max(300, min(560, self._drag_start_width - delta)))
        if width != self.panel_width:
            self.panel_width = width
            self.content_frame.grid_columnconfigure(2, minsize=self.px(width))

    def _panel_drag_end(self, _event) -> None:
        if hasattr(self, "_drag_start_x"):
            del self._drag_start_x
            self.settings["panel_width"] = self.panel_width
            self._save_settings()

    def show_settings(self) -> None:
        if self._settings_dialog is not None and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
            self._settings_dialog.focus_force()
            return
        self._settings_dialog = SettingsDialog(self)

    def show_help(self) -> None:
        if self._help_dialog is not None and self._help_dialog.winfo_exists():
            self._help_dialog.lift()
            self._help_dialog.focus_force()
            return
        self._help_dialog = HelpDialog(self)

    def open_github(self) -> None:
        webbrowser.open("https://github.com/11ly322/ncmelt")

    def open_logs(self) -> None:
        try:
            open_in_explorer(log_path().parent)
        except Exception as exc:
            messagebox.showerror("无法打开日志", str(exc), parent=self)

    def _reset_window(self) -> None:
        self._set_window_geometry()

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------
    def _register_drop_tree(self, widget=None) -> None:
        if widget is None:
            widget = self
        try:
            key = str(widget)
        except Exception:
            return
        if key in self._dnd_registered:
            return
        self._dnd_registered.add(key)
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<DropEnter>>", self._on_drag_enter)
            widget.dnd_bind("<<DropLeave>>", self._on_drag_leave)
            widget.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass
        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            self._register_drop_tree(child)

    def _on_drag_enter(self, _event):
        if self._drag_hide_job is not None:
            try:
                self.after_cancel(self._drag_hide_job)
            except ValueError:
                pass
            self._drag_hide_job = None
        self._set_status("松开以添加 NCM 文件", T.ACCENT)
        return COPY

    def _on_drag_leave(self, _event):
        if self._drag_hide_job is not None:
            try:
                self.after_cancel(self._drag_hide_job)
            except ValueError:
                pass
        self._drag_hide_job = self.after(140, self._finish_drag_leave)
        return COPY

    def _finish_drag_leave(self) -> None:
        self._drag_hide_job = None
        if not self.converting:
            self._set_status("就绪", T.MUTED)

    def _on_drop(self, event):
        self._finish_drag_leave()
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [event.data]
        signature = (time.monotonic(), "|".join(paths))
        if (
            signature[1] == self._last_drop[1]
            and time.monotonic() - self._last_drop[0] < 0.8
        ):
            return COPY
        self._last_drop = signature
        self.add_paths(paths)
        return COPY

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------
    def toggle_conversion(self) -> None:
        if self.converting:
            self._request_cancel()
        else:
            self.start_conversion()

    def start_conversion(self) -> None:
        if self.converting:
            return
        if not self.items:
            self._set_status("请先添加 NCM 文件", T.WARNING)
            return
        if self.output_mode == "custom" and not self.output_dir:
            self.choose_output_dir()
            if not self.output_dir:
                return
        pending = [
            item
            for item in self.items
            if item.is_pending and not item.is_invalid
        ]
        if not pending:
            done = [item for item in self.items if item.is_done]
            if not done:
                self._set_status("没有可转换的文件", T.WARNING)
                return
            if not messagebox.askyesno(
                "重新转换",
                f"队列中的 {len(done)} 个文件都已转换完成。\n是否使用当前设置重新转换？",
                parent=self,
            ):
                return
            for item in done:
                self._reset_item(item)
            pending = [
                item
                for item in self.items
                if item.is_pending and not item.is_invalid
            ]
        try:
            find_ffmpeg()
        except FFmpegNotFoundError as exc:
            messagebox.showerror("缺少 FFmpeg", exc.user_message, parent=self)
            return
        for item in pending:
            self._reset_item(item)
        self.converting = True
        self.cancel_event = threading.Event()
        self.completed_dirs.clear()
        self.batch_total = len(pending)
        self.batch_started = time.monotonic()
        self.current_index = 0
        self.side_panel.set_open_enabled(False)
        self.side_panel.set_progress(
            0, status="准备中", summary=f"共 {len(pending)} 首"
        )
        self.side_panel.select_tab("output")
        self._update_start_buttons()
        self._update_toolbar_states()
        for row in self.rows.values():
            row.remove_btn.configure(state="disabled")
        self._set_status(f"开始转换 {len(pending)} 个文件…", T.ACCENT)
        self.worker = threading.Thread(
            target=self._worker_run,
            args=(pending,),
            name="ncmelt-worker",
            daemon=True,
        )
        self.worker.start()

    def _reset_item(self, item: QueueItem) -> None:
        item.status = "ready"
        item.progress = 0.0
        item.output = None
        item.media = None
        item.error = ""
        row = self.rows.get(item.path)
        if row:
            row.refresh()

    def _worker_run(self, pending: list[QueueItem]) -> None:
        total = len(pending)
        success = 0
        failed = 0
        cancelled = False
        for index, item in enumerate(pending):
            if self.cancel_event is not None and self.cancel_event.is_set():
                cancelled = True
                break
            self.events.put(
                {"type": "file_start", "path": item.path, "index": index}
            )
            current_index = index

            def on_stage(stage, path=item.path):
                self.events.put({"type": "stage", "path": path, "stage": stage})

            def on_progress(fraction, path=item.path, idx=current_index):
                self.events.put(
                    {
                        "type": "progress",
                        "path": path,
                        "index": idx,
                        "fraction": fraction,
                        "overall": (idx + fraction) / total if total else 0,
                    }
                )

            try:
                outcome = convert_ncm(
                    item.path,
                    None if self.output_mode == "source" else self.output_dir,
                    self.format_id,
                    self.quality_id,
                    naming=self.naming,
                    overwrite_existing=self.overwrite_existing,
                    write_tags=self.write_tags,
                    embed_cover=self.embed_cover,
                    cancel_event=self.cancel_event,
                    on_stage=on_stage,
                    on_progress=on_progress,
                )
            except ConversionCancelled:
                self.events.put({"type": "file_cancelled", "path": item.path})
                cancelled = True
                break
            except Exception as exc:
                LOG.exception("Conversion failed: %s", item.path)
                message = (
                    exc.user_message
                    if isinstance(exc, ConverterError)
                    else str(exc)
                )
                self.events.put(
                    {"type": "file_failed", "path": item.path, "error": message}
                )
                failed += 1
                self.events.put(
                    {
                        "type": "progress",
                        "path": item.path,
                        "index": index,
                        "fraction": 1.0,
                        "overall": (index + 1) / total if total else 0,
                    }
                )
                continue
            self.events.put(
                {"type": "file_done", "path": item.path, "outcome": outcome}
            )
            success += 1
            self.events.put(
                {
                    "type": "progress",
                    "path": item.path,
                    "index": index,
                    "fraction": 1.0,
                    "overall": (index + 1) / total if total else 0,
                }
            )
        self.events.put(
            {
                "type": "batch_done",
                "success": success,
                "failed": failed,
                "cancelled": cancelled,
                "total": total,
            }
        )

    def _drain_events(self) -> None:
        try:
            while True:
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                self._handle_event(event)
        finally:
            if not self._closing:
                self.after(60, self._drain_events)

    def _find_item(self, path) -> QueueItem | None:
        if path is None:
            return None
        target = Path(path)
        return next((item for item in self.items if item.path == target), None)

    def _handle_event(self, event: dict) -> None:
        kind = event.get("type")
        item = self._find_item(event.get("path"))
        if kind == "file_start" and item:
            item.status = "decrypt"
            item.progress = 0.0
            self.current_index = int(event.get("index", 0))
            row = self.rows.get(item.path)
            if row:
                row.refresh()
            self.side_panel.set_progress(
                self.current_index / max(1, self.batch_total),
                status=f"正在解密 {self.current_index + 1}/{self.batch_total}",
                summary=f"正在处理：{truncate(item.title, 32)}",
            )
            self._set_status(
                f"正在转换 {self.current_index + 1}/{self.batch_total} · {truncate(item.title, 28)}",
                T.ACCENT,
            )
        elif kind == "stage" and item:
            item.status = event.get("stage", "encode")
            row = self.rows.get(item.path)
            if row:
                row.refresh()
        elif kind == "progress" and item:
            item.progress = float(event.get("fraction", 0))
            overall = float(event.get("overall", 0))
            row = self.rows.get(item.path)
            if row:
                row.refresh()
            stage = {
                "decrypt": "正在解密",
                "encode": "正在转换",
                "verify": "正在校验",
            }.get(item.status, "正在转换")
            self.side_panel.set_progress(
                overall,
                status=f"{stage} {round(item.progress * 100)}%",
                summary=f"正在处理：{truncate(item.title, 32)}",
            )
            self._set_status(
                f"转换中 {round(overall * 100)}% · {truncate(item.title, 28)}",
                T.ACCENT,
            )
        elif kind == "file_done" and item:
            outcome = event["outcome"]
            item.status = "done"
            item.output = outcome.output
            item.media = outcome.media
            item.progress = 1.0
            if outcome.output.parent not in self.completed_dirs:
                self.completed_dirs.append(outcome.output.parent)
            row = self.rows.get(item.path)
            if row:
                row.refresh()
            self.side_panel.set_open_enabled(True)
            self._refresh_queue_ui()
        elif kind == "file_failed" and item:
            item.status = "failed"
            item.error = event.get("error") or "转换失败"
            row = self.rows.get(item.path)
            if row:
                row.refresh()
            self._set_status(f"转换失败：{item.path.name}", T.ERROR)
        elif kind == "file_cancelled" and item:
            item.status = "cancelled"
            row = self.rows.get(item.path)
            if row:
                row.refresh()
        elif kind == "batch_done":
            self._finish_batch(
                int(event.get("success", 0)),
                int(event.get("failed", 0)),
                bool(event.get("cancelled", False)),
            )

    def _finish_batch(self, success: int, failed: int, cancelled: bool) -> None:
        elapsed = (
            time.monotonic() - self.batch_started
            if self.batch_started
            else 0
        )
        self.converting = False
        self.worker = None
        self.cancel_event = None
        for row in self.rows.values():
            row.remove_btn.configure(state="normal")
        self.side_panel.set_open_enabled(bool(self.completed_dirs))
        self._update_start_buttons()
        self._update_toolbar_states()
        self._refresh_queue_ui()
        if cancelled:
            self.side_panel.set_progress(
                None,
                status="已取消",
                percent=False,
                summary=f"已完成 {success} 首，其余文件未转换。",
            )
            self._set_status("转换已取消", T.WARNING)
        elif failed and not success:
            self.side_panel.set_progress(
                1.0,
                status="转换失败",
                summary=f"{failed} 首失败，请查看文件行中的原因。",
            )
            self._set_status(f"{failed} 个文件转换失败", T.ERROR)
        elif failed:
            self.side_panel.set_progress(
                1.0,
                status="部分完成",
                summary=f"完成 {success} 首，失败 {failed} 首；再次开始可重试。",
            )
            self._set_status(f"完成 {success} 首，{failed} 首失败", T.WARNING)
        else:
            self.side_panel.set_progress(
                1.0,
                status="全部完成",
                summary=f"完成 {success} 首 · 用时 {elapsed:.1f} 秒 · 原 NCM 未改动。",
            )
            self._set_status(f"转换完成，共 {success} 首", T.SUCCESS)
        self._save_settings()
        if success and self.auto_open and self.completed_dirs:
            self.after(220, lambda: self.open_outputs(silent=True))

    def _request_cancel(self) -> None:
        if not self.converting or self.cancel_event is None:
            return
        if not self.cancel_event.is_set():
            self.cancel_event.set()
            for button in (self.top_start_btn, self.side_panel.start_btn):
                button.configure(text="正在取消…", state="disabled")
            self.side_panel.set_progress(
                None, status="正在取消…", percent=False
            )
            self._set_status("正在取消转换…", T.WARNING)

    # ------------------------------------------------------------------
    # Output / status / close
    # ------------------------------------------------------------------
    def open_outputs(self, silent: bool = False) -> None:
        dirs = list(dict.fromkeys(self.completed_dirs))
        if not dirs:
            if not silent:
                messagebox.showinfo(
                    "暂无输出", "还没有转换完成的文件。", parent=self
                )
            return
        try:
            open_in_explorer(dirs[0])
        except Exception as exc:
            if not silent:
                messagebox.showerror("无法打开目录", str(exc), parent=self)
            return
        if len(dirs) > 1:
            self._set_status(
                f"已打开首个输出目录（共 {len(dirs)} 个目录）", T.MUTED
            )
        elif not silent:
            self._set_status("已打开输出目录", T.MUTED)

    def _set_status(self, text: str, color: str = T.MUTED) -> None:
        self.status_label.configure(text=f"●  {text}", text_color=color)

    def _queue_scroll_paint(self, _event=None) -> None:
        # CTk's wheel binding runs at the "all" tag. Flush after it so newly
        # exposed canvas areas are repainted in the same frame instead of
        # leaving a short visual trail.
        if self._scroll_paint_job is not None:
            return
        self._scroll_paint_job = self.after(8, self._flush_scroll_paint)

    def _flush_scroll_paint(self) -> None:
        self._scroll_paint_job = None
        if self._closing or not self.winfo_exists():
            return
        for frame in (self.file_list, getattr(self.side_panel, "body", None)):
            if frame is None:
                continue
            try:
                canvas = frame._parent_canvas
                canvas.configure(scrollregion=canvas.bbox("all"))
                canvas.update_idletasks()
            except Exception:
                LOG.debug("Scroll repaint failed", exc_info=True)

    def _check_ffmpeg(self) -> None:
        try:
            find_ffmpeg()
            self._set_status(f"就绪  ·  {ffmpeg_version()}", T.MUTED)
        except FFmpegNotFoundError:
            self._set_status("FFmpeg 未找到，无法转换", T.ERROR)

    def _save_settings(self) -> None:
        self.settings.update(
            {
                "format": self.format_id,
                "output_mode": self.output_mode,
                "output_dir": self.output_dir,
                "auto_open": self.auto_open,
                "naming": self.naming,
                "write_tags": self.write_tags,
                "embed_cover": self.embed_cover,
                "overwrite_existing": self.overwrite_existing,
                "panel_width": self.panel_width,
                "panel_visible": self.panel_visible,
            }
        )
        self.settings.setdefault("qualities", {})[
            self.format_id
        ] = self.quality_id
        save_settings(self.settings)

    def _on_close(self) -> None:
        if self.converting:
            if not messagebox.askyesno(
                "正在转换",
                "转换尚未完成，退出会取消当前任务。\n确定要退出吗？",
                parent=self,
            ):
                return
            self._closing = True
            self._close_deadline = time.monotonic() + 5
            self._request_cancel()
            self.after(100, self._wait_close)
            return
        self._save_settings()
        self.destroy()

    def _wait_close(self) -> None:
        if (
            self.worker is not None
            and self.worker.is_alive()
            and time.monotonic() < self._close_deadline
        ):
            self.after(100, self._wait_close)
            return
        self._save_settings()
        self.destroy()


def run(initial_paths: list[str] | None = None) -> None:
    app = ConverterApp()
    if initial_paths:
        app.after(350, lambda: app.add_paths(list(initial_paths)))
    app.mainloop()
