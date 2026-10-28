"""Right-hand conversion panel and settings/help dialogs."""

from __future__ import annotations

import logging
import webbrowser

import customtkinter as ctk

from . import APP_SUBTITLE, __version__ as APP_VERSION
from . import theme as T
from .formats import OUTPUT_FORMATS, format_by_id
from .ui_components import SummaryBars, human_size, shrink_path

LOG = logging.getLogger(__name__)


class SidePanel(ctk.CTkFrame):
    TABS = (("output", "输出"), ("meta", "元数据"), ("options", "选项"))

    def __init__(self, master, app):
        super().__init__(master, fg_color=T.PANEL, corner_radius=0)
        self.app = app
        self.active_tab = "output"
        self._format_buttons: dict[str, ctk.CTkButton] = {}
        self._quality_rows: dict[str, ctk.CTkFrame] = {}
        self._naming_buttons: dict[str, ctk.CTkButton] = {}
        self._overwrite_buttons: dict[str, ctk.CTkButton] = {}
        self._scroll_job: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header()
        self._build_summary()
        self._build_tabs()
        self._build_body()
        self._build_actions()
        self._build_output_tab()
        self._build_meta_tab()
        self._build_options_tab()
        self.select_tab("output")
        self.refresh_format()
        self.refresh_switches()
        self.set_output_display()
        self.bind("<Configure>", self._schedule_scrollbar, add="+")
        self.body.bind("<Configure>", self._schedule_scrollbar, add="+")
        self.body._parent_canvas.bind(
            "<Configure>", self._schedule_scrollbar, add="+"
        )
        self.after(200, self._sync_scrollbar)

    def p(self, value: int) -> int:
        return self.app.px(value)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent", height=38)
        header.grid(row=0, column=0, sticky="ew", padx=self.p(14))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="转换",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=14, weight="bold"),
            text_color=T.TEXT,
        ).grid(row=0, column=0, sticky="w", pady=(self.p(7), 0))
        ctk.CTkLabel(
            header,
            text=f"v{APP_VERSION}",
            anchor="e",
            font=ctk.CTkFont(family=T.FONT_MONO, size=9),
            text_color=T.SUBTLE,
        ).grid(row=0, column=1, sticky="e", pady=(self.p(7), 0))

    def _build_summary(self) -> None:
        summary = ctk.CTkFrame(self, fg_color=T.PANEL_DEEP, corner_radius=0)
        summary.grid(row=1, column=0, sticky="ew", padx=self.p(12), pady=(self.p(6), 0))
        summary.grid_columnconfigure(1, weight=1)
        self.count_label = ctk.CTkLabel(
            summary,
            text="0",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=20, weight="bold"),
            text_color=T.TEXT,
        )
        self.count_label.grid(row=0, column=0, sticky="w", padx=(self.p(10), 4), pady=(self.p(4), 0))
        ctk.CTkLabel(
            summary,
            text="个文件",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.MUTED,
        ).grid(row=0, column=1, sticky="sw", pady=(self.p(5), self.p(2)))
        self.done_label = ctk.CTkLabel(
            summary,
            text="0 完成",
            anchor="e",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUCCESS,
        )
        self.done_label.grid(row=0, column=2, sticky="e", padx=(0, self.p(10)), pady=(self.p(6), 0))

        self.bars = SummaryBars(summary, self.app)
        self.bars.grid(row=1, column=0, columnspan=3, sticky="ew", padx=self.p(10), pady=(self.p(1), self.p(3)))

        self.stats_label = ctk.CTkLabel(
            summary,
            text="总时长 00:00  ·  源文件 0 B",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        )
        self.stats_label.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=self.p(10),
            pady=(0, self.p(5)),
        )

    def _build_tabs(self) -> None:
        tabs = ctk.CTkFrame(self, fg_color="transparent", height=30)
        tabs.grid(row=2, column=0, sticky="ew", padx=self.p(12), pady=(self.p(4), 0))
        self._tab_buttons: dict[str, ctk.CTkButton] = {}
        for index, (key, label) in enumerate(self.TABS):
            btn = ctk.CTkButton(
                tabs,
                text=label,
                width=56,
                height=26,
                corner_radius=3,
                fg_color="transparent",
                hover_color=T.ROW_HOVER,
                text_color=T.MUTED,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
                command=lambda k=key: self.select_tab(k),
            )
            btn.grid(row=0, column=index, sticky="ew", padx=(0, self.p(3)))
            tabs.grid_columnconfigure(index, weight=1)
            self._tab_buttons[key] = btn

    def _build_body(self) -> None:
        self.body = ctk.CTkScrollableFrame(
            self,
            fg_color=T.PANEL,
            corner_radius=0,
            scrollbar_fg_color="transparent",
            scrollbar_button_color=T.BORDER,
            scrollbar_button_hover_color=T.SUBTLE,
        )
        self.body.grid(row=3, column=0, sticky="nsew")
        self.body.grid_columnconfigure(0, weight=1)
        self._tab_frames: dict[str, ctk.CTkFrame] = {}
        for key, _label in self.TABS:
            frame = ctk.CTkFrame(self.body, fg_color="transparent")
            frame.grid_columnconfigure(0, weight=1)
            self._tab_frames[key] = frame

    def _build_actions(self) -> None:
        actions = ctk.CTkFrame(self, fg_color=T.PANEL_DEEP, corner_radius=0)
        actions.grid(row=4, column=0, sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(actions, height=1, fg_color=T.BORDER).grid(
            row=0, column=0, columnspan=2, sticky="ew"
        )
        head = ctk.CTkFrame(actions, fg_color="transparent")
        head.grid(row=1, column=0, columnspan=2, sticky="ew", padx=self.p(12), pady=(self.p(6), 0))
        head.grid_columnconfigure(0, weight=1)
        self.action_status = ctk.CTkLabel(
            head,
            text="就绪",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.MUTED,
        )
        self.action_status.grid(row=0, column=0, sticky="w")
        self.percent_label = ctk.CTkLabel(
            head,
            text="0%",
            anchor="e",
            font=ctk.CTkFont(family=T.FONT_MONO, size=9),
            text_color=T.SUBTLE,
        )
        self.percent_label.grid(row=0, column=1, sticky="e")
        self.progress = ctk.CTkProgressBar(
            actions,
            height=(4),
            corner_radius=0,
            fg_color=T.BORDER_SOFT,
            progress_color=T.ACCENT,
        )
        self.progress.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=self.p(12), pady=(self.p(4), 0)
        )
        self.progress.set(0)
        self.summary_label = ctk.CTkLabel(
            actions,
            text="添加 NCM 文件后即可开始",
            anchor="w",
            justify="left",
            wraplength=(300),
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        )
        self.summary_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=self.p(12),
            pady=(self.p(3), self.p(3)),
        )
        out_row = ctk.CTkFrame(actions, fg_color="transparent")
        out_row.grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=self.p(12), pady=(0, self.p(5))
        )
        out_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            out_row,
            text="输出",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=8),
            text_color=T.SUBTLE,
        ).grid(row=0, column=0, sticky="w")
        self.output_label = ctk.CTkLabel(
            out_row,
            text="与源文件相同",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=8),
            text_color=T.TEXT_SOFT,
            cursor="hand2",
        )
        self.output_label.grid(row=0, column=1, sticky="ew", padx=(self.p(5), 4))
        self.output_label.bind("<Button-1>", lambda _e: self.app.choose_output_dir())
        ctk.CTkButton(
            out_row,
            text="更改",
            width=44,
            height=20,
            corner_radius=2,
            fg_color="transparent",
            hover_color=T.ROW_HOVER,
            text_color=T.ACCENT,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=8),
            command=self.app.choose_output_dir,
        ).grid(row=0, column=2, sticky="e")
        self.open_btn = ctk.CTkButton(
            actions,
            text="打开目录",
            height=(30),
            corner_radius=3,
            fg_color="transparent",
            hover_color=T.ROW_HOVER,
            border_width=1,
            border_color=T.BORDER,
            text_color=T.TEXT_SOFT,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
            command=self.app.open_outputs,
            state="disabled",
        )
        self.open_btn.grid(row=5, column=0, sticky="ew", padx=(self.p(12), self.p(4)), pady=(0, self.p(8)))
        self.start_btn = ctk.CTkButton(
            actions,
            text="开始转换",
            height=(32),
            corner_radius=3,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11, weight="bold"),
            command=self.app.toggle_conversion,
        )
        self.start_btn.grid(row=5, column=1, sticky="ew", padx=(self.p(4), self.p(12)), pady=(0, self.p(8)))
        actions.grid_columnconfigure(1, weight=2)

    # ------------------------------------------------------------------
    # Tabs content
    # ------------------------------------------------------------------
    def _section(self, parent, text: str, top: int = 12) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10, weight="bold"),
            text_color=T.TEXT_SOFT,
        ).pack(fill="x", pady=(self.p(top), self.p(6)))

    def _build_output_tab(self) -> None:
        frame = self._tab_frames["output"]
        self._section(frame, "输出格式", top=8)
        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x")
        for idx, fmt in enumerate(OUTPUT_FORMATS):
            btn = ctk.CTkButton(
                grid,
                text=fmt.label,
                width=80,
                height=30,
                corner_radius=3,
                fg_color=T.PANEL_ALT,
                hover_color=T.ROW_HOVER,
                border_width=1,
                border_color=T.BORDER,
                text_color=T.TEXT_SOFT,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
                command=lambda f=fmt.id: self.app.set_format(f),
            )
            btn.grid(
                row=idx // 3,
                column=idx % 3,
                sticky="ew",
                padx=(0 if idx % 3 == 0 else self.p(4), 0),
                pady=(0, self.p(4)),
            )
            self._format_buttons[fmt.id] = btn
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1)

        self._section(frame, "音质")
        self.quality_container = ctk.CTkFrame(frame, fg_color="transparent")
        self.quality_container.pack(fill="x")
        self.quality_hint = ctk.CTkLabel(
            frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=(300),
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        )
        self.quality_hint.pack(fill="x", pady=(self.p(4), 0))

        self.warning_label = ctk.CTkLabel(
            frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=(292),
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.WARNING,
        )

    def _switch_row(self, parent, text: str, key: str, value: bool) -> ctk.BooleanVar:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, self.p(7)))
        ctk.CTkLabel(
            row,
            text=text,
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
            text_color=T.TEXT_SOFT,
        ).pack(side="left")
        var = ctk.BooleanVar(value=value)
        switch = ctk.CTkSwitch(
            row,
            text="",
            variable=var,
            width=(38),
            switch_width=(34),
            switch_height=(17),
            progress_color=T.ACCENT,
            button_color=T.TEXT_SOFT,
            button_hover_color=T.TEXT,
            fg_color=T.BORDER,
            command=lambda k=key, v=var: self.app.set_bool_setting(k, v.get()),
        )
        switch.pack(side="right")
        return var

    def _radio_pairs(self, parent, options, current, callback) -> dict[str, ctk.CTkButton]:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        buttons: dict[str, ctk.CTkButton] = {}
        for idx, (value, label) in enumerate(options):
            btn = ctk.CTkButton(
                row,
                text=label,
                height=(30),
                corner_radius=3,
                fg_color=T.ACCENT_SOFT if value == current else T.PANEL_ALT,
                hover_color=T.ROW_HOVER,
                border_width=1,
                border_color=T.ACCENT if value == current else T.BORDER,
                text_color=T.TEXT if value == current else T.TEXT_SOFT,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
                command=lambda v=value: callback(v),
            )
            btn.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else self.p(4), 0))
            buttons[value] = btn
        return buttons

    def _build_meta_tab(self) -> None:
        frame = self._tab_frames["meta"]
        self._section(frame, "标签", top=8)
        self.tag_var = self._switch_row(frame, "写入歌曲标签", "write_tags", self.app.write_tags)
        self.cover_var = self._switch_row(frame, "嵌入封面图片", "embed_cover", self.app.embed_cover)
        self._section(frame, "文件命名")
        self._naming_buttons = self._radio_pairs(
            frame,
            (("artist-title", "歌手 - 歌名"), ("title", "仅歌名")),
            self.app.naming,
            self.app.set_naming,
        )
        ctk.CTkLabel(
            frame,
            text="MP3 / FLAC / M4A / OGG 支持完整标签；WAV 使用 ID3。",
            anchor="w",
            justify="left",
            wraplength=(300),
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        ).pack(fill="x", pady=(self.p(6), 0))

    def _build_options_tab(self) -> None:
        frame = self._tab_frames["options"]
        self._section(frame, "同名文件", top=8)
        self._overwrite_buttons = self._radio_pairs(
            frame,
            (("number", "自动编号"), ("overwrite", "覆盖已有文件")),
            "overwrite" if self.app.overwrite_existing else "number",
            self._overwrite_changed,
        )
        ctk.CTkLabel(
            frame,
            text="自动编号会生成“歌曲 (1).mp3”，不会覆盖已有文件。",
            anchor="w",
            justify="left",
            wraplength=(300),
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        ).pack(fill="x", pady=(self.p(4), 0))
        self._section(frame, "完成后")
        self.auto_var = self._switch_row(
            frame, "打开输出文件夹", "auto_open", self.app.auto_open
        )
        ctk.CTkLabel(
            frame,
            text="原 .ncm 文件始终保留，不会被移动或删除。",
            anchor="w",
            justify="left",
            wraplength=(300),
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUCCESS,
        ).pack(fill="x", pady=(self.p(7), 0))
        ctk.CTkButton(
            frame,
            text="恢复本页默认值",
            height=26,
            corner_radius=3,
            fg_color="transparent",
            hover_color=T.ROW_HOVER,
            border_width=1,
            border_color=T.BORDER,
            text_color=T.MUTED,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            command=self.app.reset_page_options,
        ).pack(fill="x", pady=(self.p(18), 0))

    def _overwrite_changed(self, value: str) -> None:
        self.app.set_overwrite(value == "overwrite")

    # ------------------------------------------------------------------
    # State refresh
    # ------------------------------------------------------------------
    def select_tab(self, key: str) -> None:
        self.active_tab = key
        for tab_key, frame in self._tab_frames.items():
            if tab_key == key:
                frame.pack(fill="x", padx=self.p(14), pady=(self.p(4), self.p(12)))
            else:
                frame.pack_forget()
        for tab_key, btn in self._tab_buttons.items():
            if tab_key == key:
                btn.configure(fg_color=T.ACCENT, text_color="#FFFFFF")
            else:
                btn.configure(fg_color="transparent", text_color=T.MUTED)
        self._schedule_scrollbar()

    def refresh_format(self) -> None:
        current = self.app.format_id
        for fmt in OUTPUT_FORMATS:
            btn = self._format_buttons[fmt.id]
            active = fmt.id == current
            btn.configure(
                fg_color=T.ACCENT if active else T.PANEL_ALT,
                text_color="#FFFFFF" if active else T.TEXT_SOFT,
                border_color=T.ACCENT if active else T.BORDER,
            )
        self._rebuild_quality_rows()
        self._refresh_output_warning()

    def _rebuild_quality_rows(self) -> None:
        for child in self.quality_container.winfo_children():
            child.destroy()
        self._quality_rows.clear()
        fmt = format_by_id(self.app.format_id)
        current = self.app.quality_id
        for quality in fmt.qualities:
            active = quality.id == current
            row = ctk.CTkFrame(
                self.quality_container,
                fg_color=T.ACCENT_SOFT if active else "transparent",
                corner_radius=0,
                height=28,
            )
            row.pack(fill="x", pady=(0, 1))
            row.pack_propagate(False)
            bar = ctk.CTkFrame(
                row,
                width=2,
                fg_color=T.ACCENT if active else "transparent",
                corner_radius=0,
            )
            bar.pack(side="left", fill="y")
            dot = ctk.CTkLabel(
                row,
                text="●" if active else "○",
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
                text_color=T.ACCENT if active else T.SUBTLE,
                width=20,
            )
            dot.pack(side="left", padx=(6, 0))
            name = ctk.CTkLabel(
                row,
                text=quality.label,
                anchor="w",
                width=100,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
                text_color=T.TEXT if active else T.TEXT_SOFT,
            )
            name.pack(side="left")
            desc = ctk.CTkLabel(
                row,
                text=quality.description,
                anchor="w",
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=8),
                text_color=T.SUBTLE,
            )
            desc.pack(side="left", fill="x", expand=True, padx=(6, 4))
            for widget in (row, dot, name, desc, bar):
                widget.bind(
                    "<Button-1>",
                    lambda _e, q=quality.id: self.app.set_quality(q),
                    add="+",
                )
            self._quality_rows[quality.id] = row
        fmt_current = fmt.quality(current)
        self.quality_hint.configure(text=fmt_current.description)

    def _refresh_output_warning(self) -> None:
        fmt = format_by_id(self.app.format_id)
        quality = fmt.quality(self.app.quality_id)
        target = quality.bitrate_kbps or 0
        if not target or fmt.lossless:
            self.warning_label.pack_forget()
            return
        low = 0
        for item in getattr(self.app, "items", []):
            header = item.header
            if header and header.container in ("mp3", "aac", "m4a", "ogg", "wma"):
                bitrate = header.metadata.bitrate if header.metadata else 0
                if bitrate and bitrate < target * 1000 * 0.9:
                    low += 1
        if low:
            self.warning_label.configure(
                text=f"{low} 首源码率低于目标，转码不会提升原始音质。"
            )
            if not self.warning_label.winfo_manager():
                self.warning_label.pack(fill="x", pady=(self.p(4), 0))
        else:
            self.warning_label.pack_forget()

    def refresh_switches(self) -> None:
        self.tag_var.set(bool(self.app.write_tags))
        self.cover_var.set(bool(self.app.embed_cover))
        self.auto_var.set(bool(self.app.auto_open))
        for value, btn in self._naming_buttons.items():
            active = value == self.app.naming
            btn.configure(
                fg_color=T.ACCENT_SOFT if active else T.PANEL_ALT,
                border_color=T.ACCENT if active else T.BORDER,
                text_color=T.TEXT if active else T.TEXT_SOFT,
            )
        for value, btn in self._overwrite_buttons.items():
            active = (value == "overwrite") == bool(self.app.overwrite_existing)
            btn.configure(
                fg_color=T.ACCENT_SOFT if active else T.PANEL_ALT,
                border_color=T.ACCENT if active else T.BORDER,
                text_color=T.TEXT if active else T.TEXT_SOFT,
            )

    def set_output_display(self) -> None:
        if self.app.output_mode == "custom" and self.app.output_dir:
            self.output_label.configure(
                text=shrink_path(self.app.output_dir, 34), text_color=T.TEXT_SOFT
            )
        else:
            self.output_label.configure(
                text="与源文件相同", text_color=T.TEXT_SOFT
            )

    def set_stats(
        self,
        count: int,
        done: int,
        invalid: int,
        seconds: float,
        size: int,
        counts: dict[str, int],
    ) -> None:
        self.count_label.configure(text=str(count))
        self.done_label.configure(
            text=f"{done} 完成" if done else (f"{invalid} 无法识别" if invalid else "0 完成"),
            text_color=T.ERROR if invalid and not done else T.SUCCESS,
        )
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        self.stats_label.configure(
            text=f"总时长 {minutes:02d}:{secs:02d}  ·  源文件 {human_size(size)}"
        )
        self.bars.set_counts(counts)

    def set_progress(
        self,
        fraction: float | None,
        status: str | None = None,
        percent: bool = True,
        summary: str | None = None,
    ) -> None:
        if fraction is not None:
            fraction = max(0.0, min(1.0, fraction))
            self.progress.set(fraction)
            if percent:
                self.percent_label.configure(text=f"{round(fraction * 100)}%")
        if status is not None:
            self.action_status.configure(text=status)
        if summary is not None:
            self.summary_label.configure(text=summary)
        self._schedule_scrollbar()

    def set_converting(self, converting: bool) -> None:
        if converting:
            self.start_btn.configure(
                text="取消转换",
                fg_color=T.ERROR_SOFT,
                hover_color="#452028",
                border_width=1,
                border_color="#7A3038",
                text_color="#FF9CA6",
            )
        else:
            self.start_btn.configure(
                text="开始转换",
                fg_color=T.ACCENT,
                hover_color=T.ACCENT_HOVER,
                border_width=0,
                text_color="#FFFFFF",
            )

    def set_start_enabled(self, enabled: bool, text: str = "开始转换") -> None:
        self.start_btn.configure(
            state="normal" if enabled else "disabled",
            text=text,
            fg_color=T.ACCENT if enabled else T.PANEL_ALT,
            hover_color=T.ACCENT_HOVER if enabled else T.PANEL_ALT,
            border_width=0 if enabled else 1,
            border_color=T.ACCENT if enabled else T.BORDER,
            text_color="#FFFFFF" if enabled else T.SUBTLE,
        )

    def set_open_enabled(self, enabled: bool) -> None:
        self.open_btn.configure(state="normal" if enabled else "disabled")

    def reset_progress(self) -> None:
        self.progress.set(0)
        self.percent_label.configure(text="0%")
        self.action_status.configure(text="就绪", text_color=T.MUTED)
        self.summary_label.configure(text="添加 NCM 文件后即可开始")

    def _schedule_scrollbar(self, _event=None) -> None:
        if self._scroll_job is not None:
            try:
                self.after_cancel(self._scroll_job)
            except ValueError:
                pass
        self._scroll_job = self.after(80, self._sync_scrollbar)

    def _sync_scrollbar(self) -> None:
        self._scroll_job = None
        try:
            first, last = self.body._parent_canvas.yview()
            needed = (last - first) < 0.999
            mapped = bool(self.body._scrollbar.winfo_ismapped())
            if needed and not mapped:
                self.body._scrollbar.grid()
            elif not needed and mapped:
                self.body._scrollbar.grid_remove()
        except Exception:
            LOG.debug("Side panel scrollbar sync failed", exc_info=True)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("设置 · ncmelt")
        self.configure(fg_color=T.BG)
        width = 760
        height = 620
        scale = max(1.0, app._get_window_scaling())
        width_px = int(round(width * scale))
        x = app.winfo_rootx() + (app.winfo_width() - width_px) // 2
        y = app.winfo_rooty() + int(50 * scale)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        try:
            icon = app.asset_icon("app.ico")
            if icon:
                self.iconbitmap(icon)
        except Exception:
            pass
        self._build()
        self.bind("<Escape>", lambda _e: self.destroy())

    def p(self, value: int) -> int:
        return self.app.px(value)

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header,
            text="设置",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=18, weight="bold"),
            text_color=T.TEXT,
        ).pack(anchor="w", padx=self.p(24), pady=(self.p(16), 0))
        ctk.CTkLabel(
            header,
            text="改动立即生效，下次启动保留",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.MUTED,
        ).pack(anchor="w", padx=self.p(24), pady=(2, self.p(14)))

        body = ctk.CTkScrollableFrame(
            self,
            fg_color=T.BG,
            corner_radius=0,
            scrollbar_button_color=T.BORDER,
            scrollbar_fg_color="transparent",
        )
        body.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(body, fg_color="transparent")
        inner.pack(fill="x", padx=self.p(24), pady=self.p(16))

        self._section(inner, "输出")
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", pady=(0, self.p(10)))
        ctk.CTkLabel(
            row, text="默认格式", width=(72), anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10), text_color=T.TEXT_SOFT
        ).pack(side="left")
        self.format_var = ctk.StringVar(value=format_by_id(self.app.format_id).label)
        ctk.CTkComboBox(
            row,
            values=[fmt.label for fmt in OUTPUT_FORMATS],
            variable=self.format_var,
            width=(160),
            height=(30),
            corner_radius=3,
            fg_color=T.PANEL_ALT,
            border_color=T.BORDER,
            button_color=T.PANEL_ALT,
            button_hover_color=T.ROW_HOVER,
            dropdown_fg_color=T.PANEL_ALT,
            dropdown_hover_color=T.ROW_HOVER,
            dropdown_text_color=T.TEXT_SOFT,
            text_color=T.TEXT,
            font=ctk.CTkFont(family=T.FONT_MONO, size=10),
            dropdown_font=ctk.CTkFont(family=T.FONT_MONO, size=10),
            state="readonly",
            command=self._format_changed,
        ).pack(side="left")
        initial_format = format_by_id(self.app.format_id)
        self.quality_var = ctk.StringVar(
            value=initial_format.quality(self.app.quality_id).label
        )
        self.quality_box = ctk.CTkComboBox(
            row,
            values=[q.label for q in initial_format.qualities],
            variable=self.quality_var,
            width=(150),
            height=(30),
            corner_radius=3,
            fg_color=T.PANEL_ALT,
            border_color=T.BORDER,
            button_color=T.PANEL_ALT,
            button_hover_color=T.ROW_HOVER,
            dropdown_fg_color=T.PANEL_ALT,
            dropdown_hover_color=T.ROW_HOVER,
            dropdown_text_color=T.TEXT_SOFT,
            text_color=T.TEXT,
            font=ctk.CTkFont(family=T.FONT_MONO, size=10),
            dropdown_font=ctk.CTkFont(family=T.FONT_MONO, size=10),
            state="readonly",
            command=self._quality_changed,
        )
        self.quality_box.pack(side="left", padx=(self.p(10), 0))

        self.output_mode_buttons = self._pair(
            inner,
            (("source", "与源文件相同"), ("custom", "指定输出目录")),
            self.app.output_mode,
            self._output_mode_changed,
        )
        self.dir_label = ctk.CTkLabel(
            inner,
            text="",
            anchor="w",
            justify="left",
            wraplength=(650),
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.SUBTLE,
        )
        self.dir_label.pack(fill="x", pady=(self.p(5), self.p(3)))
        ctk.CTkButton(
            inner,
            text="选择目录…",
            width=(110),
            height=26,
            corner_radius=3,
            fg_color=T.PANEL_ALT,
            hover_color=T.ROW_HOVER,
            border_width=1,
            border_color=T.BORDER,
            text_color=T.TEXT_SOFT,
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            command=self._choose_dir,
        ).pack(anchor="w")
        self._refresh_dir_label()

        self._section(inner, "行为")
        self._switch_row(inner, "写入歌曲标签", "write_tags", self.app.write_tags)
        self._switch_row(inner, "嵌入封面图片", "embed_cover", self.app.embed_cover)
        self._switch_row(inner, "完成后打开文件夹", "auto_open", self.app.auto_open)
        self.naming_buttons = self._pair(
            inner,
            (("artist-title", "歌手 - 歌名"), ("title", "仅歌名")),
            self.app.naming,
            self.app.set_naming,
        )
        self._pair(
            inner,
            (("number", "同名自动编号"), ("overwrite", "覆盖同名文件")),
            "overwrite" if self.app.overwrite_existing else "number",
            self._overwrite_changed,
        )

        self._section(inner, "关于")
        ctk.CTkLabel(
            inner,
            text=f"ncmelt {APP_VERSION}  ·  {APP_SUBTITLE}",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
            text_color=T.TEXT_SOFT,
        ).pack(fill="x")
        link = ctk.CTkLabel(
            inner,
            text="github.com/11ly322/ncmelt",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_MONO, size=9),
            text_color=T.ACCENT,
            cursor="hand2",
        )
        link.pack(fill="x", pady=(2, 0))
        link.bind(
            "<Button-1>",
            lambda _e: webbrowser.open("https://github.com/11ly322/ncmelt"),
        )

        footer = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0)
        footer.pack(fill="x")
        ctk.CTkButton(
            footer,
            text="完成",
            width=(120),
            height=(32),
            corner_radius=3,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11, weight="bold"),
            command=self._done,
        ).pack(pady=self.p(12))

    def _section(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11, weight="bold"),
            text_color=T.TEXT_SOFT,
        ).pack(fill="x", pady=(self.p(12), self.p(7)))

    def _pair(self, parent, options, current, callback):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, self.p(5)))
        buttons = {}
        for idx, (value, label) in enumerate(options):
            btn = ctk.CTkButton(
                row,
                text=label,
                height=(29),
                corner_radius=3,
                fg_color=T.ACCENT_SOFT if value == current else T.PANEL_ALT,
                hover_color=T.ROW_HOVER,
                border_width=1,
                border_color=T.ACCENT if value == current else T.BORDER,
                text_color=T.TEXT if value == current else T.TEXT_SOFT,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
                command=lambda v=value: callback(v),
            )
            btn.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else self.p(5), 0))
            buttons[value] = btn
        return buttons

    def _switch_row(self, parent, text: str, key: str, value: bool) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, self.p(5)))
        ctk.CTkLabel(
            row, text=text, anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10), text_color=T.TEXT_SOFT
        ).pack(side="left")
        var = ctk.BooleanVar(value=value)
        ctk.CTkSwitch(
            row,
            text="",
            variable=var,
            width=(38),
            switch_width=(34),
            switch_height=(17),
            progress_color=T.ACCENT,
            button_color=T.TEXT_SOFT,
            button_hover_color=T.TEXT,
            fg_color=T.BORDER,
            command=lambda: self.app.set_bool_setting(key, var.get()),
        ).pack(side="right")

    def _format_changed(self, label: str) -> None:
        fmt = next((item for item in OUTPUT_FORMATS if item.label == label), None)
        if fmt is None:
            return
        self.app.set_format(fmt.id)
        fmt = format_by_id(self.app.format_id)
        self.quality_box.configure(values=[q.label for q in fmt.qualities])
        quality_label = fmt.quality(self.app.quality_id).label
        self.quality_var.set(quality_label)
        self.quality_box.set(quality_label)

    def _quality_changed(self, label: str) -> None:
        fmt = format_by_id(self.app.format_id)
        quality = next((q for q in fmt.qualities if q.label == label), None)
        if quality is not None:
            self.app.set_quality(quality.id)

    def _output_mode_changed(self, mode: str) -> None:
        self.app.set_output_mode(mode)
        self._refresh_dir_label()
        self._refresh_output_mode_buttons()

    def _refresh_output_mode_buttons(self) -> None:
        for value, btn in self.output_mode_buttons.items():
            active = value == self.app.output_mode
            btn.configure(
                fg_color=T.ACCENT_SOFT if active else T.PANEL_ALT,
                border_color=T.ACCENT if active else T.BORDER,
                text_color=T.TEXT if active else T.TEXT_SOFT,
            )

    def _choose_dir(self) -> None:
        self.app.choose_output_dir()
        self._refresh_dir_label()
        self._refresh_output_mode_buttons()

    def _refresh_dir_label(self) -> None:
        if self.app.output_mode == "custom" and self.app.output_dir:
            text = self.app.output_dir
        else:
            text = "与源文件相同"
        self.dir_label.configure(text=text)

    def _overwrite_changed(self, value: str) -> None:
        self.app.set_overwrite(value == "overwrite")

    def _done(self) -> None:
        self.app.side_panel.refresh_switches()
        self.app.side_panel.set_output_display()
        self.destroy()


class HelpDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("使用说明 · ncmelt")
        self.configure(fg_color=T.BG)
        scale = max(1.0, app._get_window_scaling())
        width, height = 700, 560
        width_px = int(round(width * scale))
        x = app.winfo_rootx() + (app.winfo_width() - width_px) // 2
        y = app.winfo_rooty() + int(60 * scale)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.transient(app)
        self.grab_set()
        self.bind("<Escape>", lambda _e: self.destroy())
        header = ctk.CTkFrame(self, fg_color=T.PANEL, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header,
            text="使用说明",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=18, weight="bold"),
            text_color=T.TEXT,
            anchor="w",
        ).pack(fill="x", padx=app.px(24), pady=(app.px(16), app.px(4)))
        ctk.CTkLabel(
            header,
            text="NCM to MP3 converter",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=9),
            text_color=T.MUTED,
            anchor="w",
        ).pack(fill="x", padx=app.px(24), pady=(0, app.px(14)))
        body = ctk.CTkFrame(self, fg_color=T.BG)
        body.pack(fill="both", expand=True, padx=app.px(24), pady=app.px(16))
        lines = [
            ("1", "把 .ncm 文件拖到窗口任意位置，或使用 文件 → 添加文件（Ctrl+O）。"),
            ("2", "在右侧选择输出格式和质量，确认输出目录。"),
            ("3", "点击“开始转换”。完成后可以打开输出目录。"),
        ]
        for number, text in lines:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=(0, app.px(10)))
            ctk.CTkLabel(
                row,
                text=number,
                width=24,
                height=24,
                corner_radius=12,
                fg_color=T.ACCENT,
                text_color="#FFFFFF",
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=9, weight="bold"),
            ).pack(side="left", anchor="n")
            ctk.CTkLabel(
                row,
                text=text,
                anchor="w",
                justify="left",
                wraplength=590,
                font=ctk.CTkFont(family=T.FONT_FAMILY, size=10),
                text_color=T.TEXT_SOFT,
            ).pack(side="left", padx=(app.px(10), 0))
        ctk.CTkLabel(
            body,
            text="快捷键",
            anchor="w",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=10, weight="bold"),
            text_color=T.TEXT,
        ).pack(fill="x", pady=(app.px(4), app.px(4)))
        ctk.CTkLabel(
            body,
            text="Ctrl+O  添加文件    Ctrl+Shift+O  添加文件夹    Ctrl+Enter  开始/取消\n"
            "Delete  移除选中    Ctrl+A  全选    Ctrl+B  显示/隐藏面板    F1  使用说明",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(family=T.FONT_MONO, size=9),
            text_color=T.MUTED,
        ).pack(fill="x")
        ctk.CTkButton(
            self,
            text="知道了",
            width=120,
            height=34,
            corner_radius=3,
            fg_color=T.ACCENT,
            hover_color=T.ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=T.FONT_FAMILY, size=11, weight="bold"),
            command=self.destroy,
        ).pack(pady=app.px(10))
