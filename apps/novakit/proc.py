"""Uruchamianie poleceń systemowych: synchronicznie i asynchronicznie (QProcess)."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


@dataclass
class Result:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def which(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list[str] | str, timeout: float = 30, input_text: str | None = None,
        env: dict[str, str] | None = None) -> Result:
    """Uruchamia polecenie i zwraca wynik. Nigdy nie rzuca wyjątku."""
    args = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
    if not args or not shutil.which(args[0]):
        return Result(127, "", f"command not found: {args[0] if args else ''}")
    full_env = dict(os.environ, LC_ALL="C.UTF-8") if env is None else env
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           input=input_text, env=full_env)
        return Result(p.returncode, p.stdout, p.stderr)
    except subprocess.TimeoutExpired:
        return Result(124, "", "timeout")
    except OSError as exc:
        return Result(126, "", str(exc))


def privileged(args: list[str]) -> list[str]:
    """Polecenie z uprawnieniami administratora (okno hasła polkit)."""
    if os.geteuid() == 0:
        return list(args)
    return ["pkexec", *args]


def in_live_session() -> bool:
    try:
        with open("/proc/cmdline", encoding="utf-8") as f:
            return "boot=casper" in f.read()
    except OSError:
        return False


class Task(QObject):
    """Asynchroniczne wykonanie listy poleceń jedno po drugim.

    Sygnały: line(str) – każda linia wyjścia, progress(int) – procent
    (gdy da się go odczytać), finished(bool) – czy wszystkie się powiodły.
    """

    line = Signal(str)
    progress = Signal(int)
    finished = Signal(bool)

    def __init__(self, commands: list[list[str]], parent: QObject | None = None):
        super().__init__(parent)
        self.commands = list(commands)
        self.proc: QProcess | None = None
        self._buf = ""

    def start(self) -> None:
        self._next()

    def cancel(self) -> None:
        self.commands.clear()
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()

    def _next(self) -> None:
        if not self.commands:
            self.finished.emit(True)
            return
        args = self.commands.pop(0)
        self.line.emit("$ " + " ".join(shlex.quote(a) for a in args))
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("LC_ALL", "C.UTF-8")
        env.insert("DEBIAN_FRONTEND", "noninteractive")
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._error)
        self.proc.start(args[0], args[1:])

    def _read(self) -> None:
        assert self.proc is not None
        self._buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        while True:
            idx = min((i for i in (self._buf.find("\n"), self._buf.find("\r")) if i >= 0), default=-1)
            if idx < 0:
                break
            text, self._buf = self._buf[:idx].strip(), self._buf[idx + 1:]
            if text:
                self.line.emit(text)
                pct = parse_percent(text)
                if pct is not None:
                    self.progress.emit(pct)

    def _error(self, err) -> None:
        if err == QProcess.FailedToStart:
            self.line.emit("! failed to start")
            self.commands.clear()
            self.finished.emit(False)

    def _done(self, code: int, _status) -> None:
        if self._buf.strip():
            self.line.emit(self._buf.strip())
        self._buf = ""
        if code != 0:
            self.commands.clear()
            self.finished.emit(False)
        else:
            self._next()


def parse_percent(text: str) -> int | None:
    """Wyciąga procent postępu z wyjścia apt/flatpak (np. 'Progress: [ 45%]', '45%')."""
    import re

    m = re.search(r"(\d{1,3})(?:[.,]\d+)?\s*%", text)
    if m:
        v = int(m.group(1))
        if 0 <= v <= 100:
            return v
    return None
