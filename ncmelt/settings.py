"""Persistent user settings and application paths."""

from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

APP_FOLDER = "ncmelt"
DEFAULT_SETTINGS: dict[str, Any] = {
    "format": "mp3",
    "qualities": {
        "mp3": "320",
        "flac": "standard",
        "wav": "pcm16",
        "m4a": "256",
        "ogg": "q6",
    },
    "output_mode": "source",
    "output_dir": "",
    "auto_open": False,
    "naming": "artist-title",
    "write_tags": True,
    "embed_cover": True,
    "overwrite_existing": False,
    "panel_width": 350,
    "panel_visible": True,
    "last_dir": "",
}


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_FOLDER


def local_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_FOLDER


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def log_path() -> Path:
    return local_data_dir() / "logs" / "app.log"


def load_settings() -> dict[str, Any]:
    result = dict(DEFAULT_SETTINGS)
    result["qualities"] = dict(DEFAULT_SETTINGS["qualities"])
    path = settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    if isinstance(raw, dict):
        for key in DEFAULT_SETTINGS:
            if key in raw:
                result[key] = raw[key]
    if not isinstance(result.get("qualities"), dict):
        result["qualities"] = dict(DEFAULT_SETTINGS["qualities"])
    else:
        merged = dict(DEFAULT_SETTINGS["qualities"])
        merged.update({k: v for k, v in result["qualities"].items() if isinstance(v, str)})
        result["qualities"] = merged
    if result.get("output_mode") not in ("source", "custom"):
        result["output_mode"] = "source"
    if result.get("naming") not in ("artist-title", "title"):
        result["naming"] = "artist-title"
    if not isinstance(result.get("format"), str):
        result["format"] = "mp3"
    if not isinstance(result.get("output_dir"), str):
        result["output_dir"] = ""
    if not isinstance(result.get("last_dir"), str):
        result["last_dir"] = ""
    for key in (
        "auto_open",
        "write_tags",
        "embed_cover",
        "overwrite_existing",
        "panel_visible",
    ):
        result[key] = bool(result.get(key))
    try:
        result["panel_width"] = max(300, min(560, int(result.get("panel_width", 350))))
    except (TypeError, ValueError):
        result["panel_width"] = 350
    return result


def save_settings(settings: dict[str, Any]) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temp, path)
    except OSError:
        logging.getLogger(__name__).exception("Could not save settings")


def setup_logging() -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        path, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)
