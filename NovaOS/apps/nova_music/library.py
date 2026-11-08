"""Biblioteka muzyczna: skanowanie folderów i odczyt tagów (mutagen, jeśli dostępny)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_EXT = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wav", ".wma", ".alac", ".aiff"}

try:
    import mutagen  # type: ignore
except ImportError:  # działamy też bez tagów
    mutagen = None


@dataclass
class Track:
    path: Path
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    number: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        return self.title or self.path.stem


def _first(tags, *keys) -> str:
    for k in keys:
        try:
            v = tags.get(k)
        except Exception:  # noqa: BLE001
            v = None
        if v:
            v = v[0] if isinstance(v, list) else v
            return str(getattr(v, "text", [v])[0] if hasattr(v, "text") else v)
    return ""


def read_track(path: Path) -> Track:
    t = Track(path)
    stem = path.stem
    if " - " in stem:  # "Wykonawca - Tytuł"
        t.artist, t.title = (s.strip() for s in stem.split(" - ", 1))
    if mutagen is None:
        return t
    try:
        f = mutagen.File(str(path), easy=True)
    except Exception:  # noqa: BLE001 – uszkodzony plik
        return t
    if f is None:
        return t
    if getattr(f, "info", None) is not None:
        t.duration = float(getattr(f.info, "length", 0) or 0)
    tags = f.tags or {}
    t.title = _first(tags, "title") or t.title
    t.artist = _first(tags, "artist", "albumartist") or t.artist
    t.album = _first(tags, "album") or t.album or path.parent.name
    num = _first(tags, "tracknumber")
    try:
        t.number = int(num.split("/")[0]) if num else 0
    except ValueError:
        pass
    return t


def scan(folders: list[Path]) -> list[Track]:
    tracks = []
    for folder in folders:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                if os.path.splitext(name)[1].lower() in AUDIO_EXT:
                    tracks.append(read_track(Path(root) / name))
    tracks.sort(key=lambda t: (t.artist.lower(), t.album.lower(), t.number, t.display_title.lower()))
    return tracks


def cover_art(path: Path) -> bytes | None:
    """Okładka: osadzona w pliku albo cover.jpg/folder.jpg w katalogu."""
    if mutagen is not None:
        try:
            f = mutagen.File(str(path))
            if f is not None:
                pics = getattr(f, "pictures", None)
                if pics:
                    return pics[0].data
                tags = getattr(f, "tags", None) or {}
                for key in list(tags.keys()):
                    if str(key).startswith("APIC"):
                        return tags[key].data
                    if key == "covr":
                        return bytes(tags[key][0])
        except Exception:  # noqa: BLE001
            pass
    for name in ("cover.jpg", "cover.png", "folder.jpg", "front.jpg", "Cover.jpg"):
        p = path.parent / name
        if p.is_file():
            return p.read_bytes()
    return None


def fmt_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
