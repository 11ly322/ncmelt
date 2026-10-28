"""Regenerate the README screenshots (development helper)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ncmelt.gui import ConverterApp  # noqa: E402
from ncmelt.settings import setup_logging  # noqa: E402

DOCS = ROOT / "docs"
SAMPLES = sorted((ROOT / "tests" / "generated").glob("*.ncm"))


def pump(app: ConverterApp, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        time.sleep(0.02)


def capture(app: ConverterApp, path: Path) -> None:
    app.update_idletasks()
    app.attributes("-topmost", True)
    app.lift()
    app.focus_force()
    pump(app, 0.5)
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    image.resize((1600, round(image.height * 1600 / image.width))).save(
        path, optimize=True
    )
    app.attributes("-topmost", False)
    print(path, image.size)


def main() -> None:
    setup_logging()
    DOCS.mkdir(exist_ok=True)
    app = ConverterApp()
    pump(app, 0.7)
    app.add_paths([str(path) for path in SAMPLES])
    pump(app, 0.8)
    capture(app, DOCS / "screenshot-ready.png")
    app.start_conversion()
    deadline = time.monotonic() + 120
    while app.converting and time.monotonic() < deadline:
        app.update()
        time.sleep(0.05)
    pump(app, 0.8)
    capture(app, DOCS / "screenshot-done.png")
    app._on_close()


if __name__ == "__main__":
    main()
