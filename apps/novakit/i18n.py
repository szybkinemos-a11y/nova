"""Tłumaczenia NovaOS: teksty w kodzie po angielsku, katalog polski w locale/pl.json.

Język: zmienna NOVAOS_LANG, potem LANGUAGE / LC_ALL / LC_MESSAGES / LANG.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_CATALOG: dict[str, str] = {}
LANG = "en"


def detect_language() -> str:
    for var in ("NOVAOS_LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return value.split(":")[0].split("_")[0].split(".")[0].lower() or "en"
    return "en"


def load(lang: str | None = None) -> None:
    global LANG, _CATALOG
    LANG = (lang or detect_language()) or "en"
    _CATALOG = {}
    path = Path(__file__).with_name("locale") / f"{LANG}.json"
    if path.is_file():
        try:
            _CATALOG = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            _CATALOG = {}


def tr(text: str, **kwargs) -> str:
    """Zwraca przetłumaczony tekst; parametry wstawiane przez str.format."""
    out = _CATALOG.get(text, text)
    return out.format(**kwargs) if kwargs else out


load()
