"""Przechowywanie notatek Nova Notes jako plików Markdown w ~/Dokumenty/Notatki."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from novakit.config import user_dir


@dataclass
class Note:
    path: Path

    @property
    def title(self) -> str:
        return self.path.stem

    @property
    def mtime(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0

    def read(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except OSError:
            return ""

    @property
    def pinned(self) -> bool:
        return self.read().startswith("<!-- pinned -->")


_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_name(title: str) -> str:
    name = _BAD.sub("-", title).strip().strip(".")
    return name[:120] or "Notatka"


class NoteStore:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or (user_dir("DOCUMENTS", "Documents") / "Notatki")
        self.dir.mkdir(parents=True, exist_ok=True)

    def all(self, query: str = "") -> list[Note]:
        notes = [Note(p) for p in self.dir.glob("*.md")]
        if query:
            q = query.lower()
            notes = [n for n in notes if q in n.title.lower() or q in n.read().lower()]
        return sorted(notes, key=lambda n: (not n.pinned, -n.mtime))

    def unique_path(self, title: str) -> Path:
        base = safe_name(title)
        path = self.dir / f"{base}.md"
        i = 2
        while path.exists():
            path = self.dir / f"{base} ({i}).md"
            i += 1
        return path

    def create(self, title: str | None = None) -> Note:
        title = title or time.strftime("Notatka %Y-%m-%d %H.%M")
        path = self.unique_path(title)
        path.write_text("", encoding="utf-8")
        return Note(path)

    def save(self, note: Note, text: str) -> None:
        tmp = note.path.with_suffix(".md.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, note.path)

    def rename(self, note: Note, title: str) -> Note:
        if safe_name(title) == note.title:
            return note
        new = self.unique_path(title)
        note.path.rename(new)
        return Note(new)

    def set_pinned(self, note: Note, pinned: bool) -> None:
        text = note.read()
        marker = "<!-- pinned -->\n"
        if pinned and not text.startswith("<!-- pinned -->"):
            text = marker + text
        elif not pinned and text.startswith("<!-- pinned -->"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
        self.save(note, text)

    def delete(self, note: Note) -> None:
        """Przenosi do kosza (Qt), a gdy się nie da – usuwa plik."""
        from PySide6.QtCore import QFile
        if not QFile.moveToTrash(str(note.path)):
            note.path.unlink(missing_ok=True)
