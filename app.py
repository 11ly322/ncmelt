"""Application entry point."""

from __future__ import annotations

import logging
import os
import sys


def main() -> None:
    from ncmelt.settings import setup_logging

    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        if os.name == "nt":
            try:
                import ctypes

                # Must run before Tk creates any window, otherwise a frozen
                # build scales widgets without scaling the native window.
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "ncmelt.LocalConverter.1"
                )
            except Exception:
                pass
        from ncmelt.gui import run
        from ncmelt.settings import log_path

        arguments = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
        run(initial_paths=arguments or None)
    except Exception:
        logger.exception("Unhandled application error")
        try:
            from tkinter import messagebox
            from ncmelt.settings import log_path

            messagebox.showerror(
                "程序发生错误",
                "程序遇到未处理的错误，详情已写入日志。\n\n" f"{log_path()}",
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        import multiprocessing

        multiprocessing.freeze_support()
    main()
