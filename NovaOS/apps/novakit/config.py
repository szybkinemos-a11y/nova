"""Ścieżki XDG i proste, trwałe ustawienia aplikacji w JSON."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else Path.home() / default


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "novaos"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "novaos"
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "novaos"


def user_dir(kind: str, fallback: str) -> Path:
    """Katalog użytkownika (Pobrane, Muzyka...) wg xdg-user-dirs."""
    cfg = _xdg("XDG_CONFIG_HOME", ".config") / "user-dirs.dirs"
    key = f"XDG_{kind}_DIR"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                val = line.split("=", 1)[1].strip().strip('"')
                return Path(val.replace("$HOME", str(Path.home())))
    except OSError:
        pass
    return Path.home() / fallback


class Store:
    """Ustawienia aplikacji zapisywane atomowo w ~/.config/novaos/<nazwa>.json"""

    def __init__(self, name: str, defaults: dict[str, Any] | None = None, directory: Path | None = None):
        self.path = (directory or CONFIG_DIR) / f"{name}.json"
        self.data: dict[str, Any] = dict(defaults or {})
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self.data[key] = value
        if save:
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
