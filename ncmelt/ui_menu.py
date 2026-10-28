"""A small dark popup menu used by the ncmelt toolbar."""

from __future__ import annotations

import customtkinter as ctk

from . import theme as T


class MenuPopup(ctk.CTkToplevel):
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
