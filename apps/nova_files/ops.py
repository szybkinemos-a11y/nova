"""Operacje na plikach dla Nova Files (kopiowanie/przenoszenie w wątku, nazwy kolizyjne)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal


def unique_target(dest_dir: Path, name: str) -> Path:
    """'plik.txt' -> 'plik (kopia).txt' -> 'plik (kopia 2).txt' gdy cel istnieje."""
    target = dest_dir / name
    if not target.exists():
        return target
    stem, suffix = (name, "") if (dest_dir / name).is_dir() else (Path(name).stem, Path(name).suffix)
    i = 1
    while True:
        label = "kopia" if i == 1 else f"kopia {i}"
        target = dest_dir / f"{stem} ({label}){suffix}"
        if not target.exists():
            return target
        i += 1


def dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


class TransferWorker(QObject):
    progress = Signal(int, str)
    done = Signal(bool, str)

    def __init__(self, sources: list[Path], dest: Path, move: bool):
        super().__init__()
        self.sources, self.dest, self.move = sources, dest, move

    def run(self) -> None:
        try:
            n = len(self.sources)
            for i, src in enumerate(self.sources):
                self.progress.emit(int(i * 100 / max(n, 1)), src.name)
                if self.dest == src.parent and self.move:
                    continue
                if self.dest.resolve().is_relative_to(src.resolve()) and src.is_dir():
                    raise OSError(f"Cannot copy a folder into itself: {src.name}")
                target = unique_target(self.dest, src.name)
                if self.move:
                    shutil.move(str(src), str(target))
                elif src.is_dir() and not src.is_symlink():
                    shutil.copytree(src, target, symlinks=True)
                else:
                    shutil.copy2(src, target, follow_symlinks=False)
            self.progress.emit(100, "")
            self.done.emit(True, "")
        except OSError as exc:
            self.done.emit(False, str(exc))


def start_transfer(parent, sources, dest, move, on_progress, on_done) -> QThread:
    thread = QThread(parent)
    worker = TransferWorker(sources, dest, move)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress.connect(on_progress)
    worker.done.connect(on_done)
    worker.done.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread._worker = worker  # utrzymanie referencji
    thread.start()
    return thread
