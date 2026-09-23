"""
core/config.py
Local settings for this install: last model, last folders, Roboflow credentials.

Stored as JSON in settings.json next to the app. This is a personal desktop
tool, so the key lives on disk rather than in a keyring - but it stays out of
the source tree, and settings.json is listed in .gitignore.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict

APP_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = APP_DIR / "settings.json"

DEFAULTS: Dict[str, Any] = {
    "model_weights": "",
    "model_dir": "",
    "last_dataset_dir": "",
    "last_output_dir": "",
    "roboflow_api_key": "",
    "roboflow_workspace": "",
    "roboflow_project": "",
    "confidence": 0.25,
    "autolabel_classes": [],
    "autolabel_names": {},
    "theme": "dark",
}


class Settings:
    _instance: "Settings | None" = None

    def __init__(self):
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self.load()

    @classmethod
    def instance(cls) -> "Settings":
        if cls._instance is None:
            cls._instance = Settings()
        return cls._instance

    # ------------------------------------------------------------------ io
    def load(self):
        if SETTINGS_PATH.is_file():
            try:
                stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    self._data.update(stored)
            except (OSError, json.JSONDecodeError):
                pass

    def save(self):
        try:
            SETTINGS_PATH.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError:
            pass

    # --------------------------------------------------------------- access
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any, save: bool = True):
        self._data[key] = value
        if save:
            self.save()

    def update(self, **kwargs):
        self._data.update(kwargs)
        self.save()

    # ------------------------------------------------------------- roboflow
    def roboflow_api_key(self) -> str:
        """Environment variable wins, so a key never has to be typed in at all."""
        return os.environ.get("ROBOFLOW_API_KEY", "") or self.get("roboflow_api_key", "")

    @staticmethod
    def masked(secret: str) -> str:
        if not secret:
            return "(not set)"
        return secret[:4] + "…" + secret[-3:] if len(secret) > 8 else "…"


def settings() -> Settings:
    return Settings.instance()
