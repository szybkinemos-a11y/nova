"""Zakładki, historia i ustawienia Nova Browser (JSON w ~/.local/share/novaos/browser)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from novakit.config import DATA_DIR

SEARCH_ENGINES = {
    "DuckDuckGo": "https://duckduckgo.com/?q={}",
    "Startpage": "https://www.startpage.com/do/search?q={}",
    "Google": "https://www.google.com/search?q={}",
    "Bing": "https://www.bing.com/search?q={}",
    "Brave Search": "https://search.brave.com/search?q={}",
}


def to_url(text: str, engine: str = "DuckDuckGo") -> str:
    """Zamienia wpis z paska adresu na URL (adres albo wyszukiwanie)."""
    t = text.strip()
    if not t:
        return "nova:newtab"
    if t.startswith(("http://", "https://", "file://", "about:", "nova:", "view-source:")):
        return t
    if os.path.isabs(t) and os.path.exists(t):
        return "file://" + t
    host = t.split("/")[0]
    looks_like_host = (" " not in t) and ("." in host or host.startswith("localhost") or host.count(":") == 1)
    if looks_like_host and not host.startswith("."):
        return ("http://" if host.startswith(("localhost", "127.", "192.168.", "10.")) else "https://") + t
    return SEARCH_ENGINES.get(engine, SEARCH_ENGINES["DuckDuckGo"]).format(quote_plus(t))


class JsonList:
    def __init__(self, name: str, limit: int | None = None, directory: Path | None = None):
        self.path = (directory or DATA_DIR / "browser") / f"{name}.json"
        self.limit = limit
        try:
            self.items: list[dict] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.limit:
            self.items = self.items[-self.limit:]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


class Bookmarks(JsonList):
    DEFAULTS = [
        {"title": "NovaOS", "url": "https://novaos.example.org"},
        {"title": "Wikipedia", "url": "https://pl.wikipedia.org"},
        {"title": "Flathub", "url": "https://flathub.org"},
        {"title": "Ubuntu", "url": "https://ubuntu.com"},
        {"title": "KDE", "url": "https://kde.org"},
        {"title": "OpenStreetMap", "url": "https://www.openstreetmap.org"},
    ]

    def __init__(self, directory: Path | None = None):
        super().__init__("bookmarks", directory=directory)
        if not self.path.exists():
            self.items = list(self.DEFAULTS)

    def has(self, url: str) -> bool:
        return any(b["url"] == url for b in self.items)

    def toggle(self, url: str, title: str) -> bool:
        if self.has(url):
            self.items = [b for b in self.items if b["url"] != url]
            self.save()
            return False
        self.items.append({"title": title or urlparse(url).netloc, "url": url})
        self.save()
        return True


class History(JsonList):
    def __init__(self, directory: Path | None = None):
        super().__init__("history", limit=3000, directory=directory)

    def add(self, url: str, title: str) -> None:
        if not url.startswith(("http://", "https://")):
            return
        if self.items and self.items[-1]["url"] == url:
            self.items[-1]["title"] = title
        else:
            self.items.append({"url": url, "title": title, "time": int(time.time())})
        self.save()

    def search(self, text: str, n: int = 8) -> list[dict]:
        t = text.lower()
        seen, out = set(), []
        for item in reversed(self.items):
            if item["url"] in seen:
                continue
            if t in item["url"].lower() or t in item.get("title", "").lower():
                seen.add(item["url"])
                out.append(item)
                if len(out) >= n:
                    break
        return out

    def clear(self) -> None:
        self.items = []
        self.save()
