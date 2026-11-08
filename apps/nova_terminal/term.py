"""Widżet terminala: pseudo-terminal (pty) + emulacja xterm (pyte) + rysowanie w Qt."""
from __future__ import annotations

import fcntl
import os
import pty
import signal
import struct
import termios

import pyte
from PySide6.QtCore import QPoint, QRect, QSocketNotifier, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QKeyEvent, QPainter
from PySide6.QtWidgets import QWidget

# Paleta Nova (16 kolorów ANSI)
NOVA_COLORS = {
    "black": "#1B1828", "red": "#F87171", "green": "#34D399", "brown": "#FBBF24", "yellow": "#FBBF24",
    "blue": "#60A5FA", "magenta": "#C084FC", "cyan": "#22D3EE", "white": "#D9D6F0",
    "brightblack": "#5B5675", "brightred": "#FCA5A5", "brightgreen": "#6EE7B7", "brightbrown": "#FDE68A",
    "brightyellow": "#FDE68A", "brightblue": "#93C5FD", "brightmagenta": "#D8B4FE",
    "brightcyan": "#67E8F9", "brightwhite": "#FFFFFF",
}
DEFAULT_FG = "#ECEBF5"
DEFAULT_BG = "#0F0D17"
CURSOR = "#7B61FF"

KEYMAP = {
    Qt.Key_Return: b"\r", Qt.Key_Enter: b"\r", Qt.Key_Backspace: b"\x7f", Qt.Key_Tab: b"\t",
    Qt.Key_Escape: b"\x1b", Qt.Key_Insert: b"\x1b[2~", Qt.Key_Delete: b"\x1b[3~",
    Qt.Key_PageUp: b"\x1b[5~", Qt.Key_PageDown: b"\x1b[6~",
    Qt.Key_F1: b"\x1bOP", Qt.Key_F2: b"\x1bOQ", Qt.Key_F3: b"\x1bOR", Qt.Key_F4: b"\x1bOS",
    Qt.Key_F5: b"\x1b[15~", Qt.Key_F6: b"\x1b[17~", Qt.Key_F7: b"\x1b[18~", Qt.Key_F8: b"\x1b[19~",
    Qt.Key_F9: b"\x1b[20~", Qt.Key_F10: b"\x1b[21~", Qt.Key_F11: b"\x1b[23~", Qt.Key_F12: b"\x1b[24~",
}
CURSOR_KEYS = {Qt.Key_Up: "A", Qt.Key_Down: "B", Qt.Key_Right: "C", Qt.Key_Left: "D", Qt.Key_Home: "H", Qt.Key_End: "F"}
BRACKETED_PASTE = 2004 << 5   # tryb prywatny w pyte jest przesunięty o 5 bitów


def color(name: str, default: str) -> QColor:
    if name == "default":
        return QColor(default)
    if name in NOVA_COLORS:
        return QColor(NOVA_COLORS[name])
    if len(name) == 6:
        return QColor("#" + name)
    return QColor(default)


class TerminalWidget(QWidget):
    title_changed = Signal(str)
    closed = Signal()

    def __init__(self, cwd: str | None = None, command: list[str] | None = None, font_size: int = 11):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setCursor(Qt.IBeamCursor)
        self.font_ = QFont("Noto Sans Mono")
        self.font_.setStyleHint(QFont.Monospace)
        self.font_.setFixedPitch(True)
        self.font_.setPointSize(font_size)
        self._metrics()
        self.cols, self.rows = 80, 24
        self.screen = pyte.HistoryScreen(self.cols, self.rows, history=5000, ratio=0.5)
        self.screen.set_mode(pyte.modes.LNM)
        self.screen.write_process_input = self._write_str
        self.stream = pyte.ByteStream(self.screen)
        self.scroll = 0                      # ile linii historii przewinięto w górę
        self.sel_start: QPoint | None = None  # zaznaczenie w komórkach (kolumna, wiersz widoku)
        self.sel_end: QPoint | None = None
        self.last_title = ""
        self.blink = True
        self._repaint = QTimer(self, singleShot=True, interval=12, timeout=self.update)
        QTimer(self, interval=600, timeout=self._blink).start()
        self._spawn(cwd, command)

    # ------------------------------------------------------------ proces
    def _spawn(self, cwd, command) -> None:
        shell = command or [os.environ.get("SHELL", "/bin/bash")]
        pid, fd = pty.fork()
        if pid == 0:  # proces potomny
            if cwd and os.path.isdir(cwd):
                os.chdir(cwd)
            env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor", TERM_PROGRAM="NovaTerminal")
            env.pop("PYTHONPATH", None)
            try:
                os.execvpe(shell[0], shell, env)
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        self.notifier = QSocketNotifier(fd, QSocketNotifier.Read, self)
        self.notifier.activated.connect(self._read)

    def _read(self) -> None:
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self.notifier.setEnabled(False)
            try:
                os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                pass
            self.closed.emit()
            return
        self.stream.feed(data)
        if self.scroll:
            self.scroll = 0
        if self.screen.title != self.last_title:
            self.last_title = self.screen.title
            self.title_changed.emit(self.last_title)
        self._repaint.start()

    def write(self, data: bytes) -> None:
        try:
            os.write(self.fd, data)
        except OSError:
            pass

    def _write_str(self, text: str) -> None:
        self.write(text.encode())

    def terminate(self) -> None:
        try:
            os.kill(self.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass

    def cwd(self) -> str | None:
        """Bieżący katalog powłoki (do otwierania nowej karty w tym samym miejscu)."""
        try:
            return os.readlink(f"/proc/{self.pid}/cwd")
        except OSError:
            return None

    # ------------------------------------------------------------ geometria
    def _metrics(self) -> None:
        fm = QFontMetricsF(self.font_)
        self.cw = fm.horizontalAdvance("M")
        self.ch = fm.height()
        self.ascent = fm.ascent()

    def set_font_size(self, size: int) -> None:
        self.font_.setPointSize(max(6, min(size, 40)))
        self._metrics()
        self.resizeEvent(None)

    def resizeEvent(self, _ev) -> None:
        cols = max(10, int((self.width() - 12) // self.cw))
        rows = max(3, int((self.height() - 8) // self.ch))
        if (cols, rows) != (self.cols, self.rows):
            self.cols, self.rows = cols, rows
            self.screen.resize(rows, cols)
            if hasattr(self, "fd"):
                fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.update()

    # ------------------------------------------------------------ rysowanie
    def _visible_lines(self):
        hist = list(self.screen.history.top)
        buf = [self.screen.buffer[y] for y in range(self.rows)]
        if self.scroll:
            start = len(hist) - self.scroll
            lines = hist[start:] + buf
            return lines[: self.rows]
        return buf

    def _selected(self, x: int, y: int) -> bool:
        if not self.sel_start or not self.sel_end:
            return False
        a, b = sorted([(self.sel_start.y(), self.sel_start.x()), (self.sel_end.y(), self.sel_end.x())])
        return a <= (y, x) <= b

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        bg_default = QColor(DEFAULT_BG)
        p.fillRect(self.rect(), bg_default)
        p.setFont(self.font_)
        ox, oy = 6, 4
        sel_bg = QColor(CURSOR)
        sel_bg.setAlpha(110)
        for y, line in enumerate(self._visible_lines()):
            x = 0
            while x < self.cols:
                ch = line[x]
                fg = color(ch.fg, DEFAULT_FG)
                bg = color(ch.bg, DEFAULT_BG)
                if ch.reverse:
                    fg, bg = bg, fg
                if ch.bold and ch.fg in NOVA_COLORS and not ch.fg.startswith("bright"):
                    fg = color("bright" + ch.fg, DEFAULT_FG)
                # zbierz ciąg znaków o tych samych atrybutach
                run = ch.data
                x2 = x + 1
                while x2 < self.cols:
                    c2 = line[x2]
                    if (c2.fg, c2.bg, c2.bold, c2.reverse, c2.underscore) != (ch.fg, ch.bg, ch.bold, ch.reverse, ch.underscore) \
                            or self._selected(x2, y) != self._selected(x, y):
                        break
                    run += c2.data
                    x2 += 1
                rect = QRect(int(ox + x * self.cw), int(oy + y * self.ch), int((x2 - x) * self.cw + 1), int(self.ch + 1))
                if bg != bg_default:
                    p.fillRect(rect, bg)
                if self._selected(x, y):
                    p.fillRect(rect, sel_bg)
                if run.strip():
                    f = p.font()
                    f.setBold(ch.bold)
                    f.setUnderline(ch.underscore)
                    p.setFont(f)
                    p.setPen(fg)
                    # rysowanie znak po znaku gwarantuje siatkę przy znakach szerokich/złożonych
                    for i, c in enumerate(run):
                        if c != " ":
                            p.drawText(int(ox + (x + i) * self.cw), int(oy + y * self.ch + self.ascent), c)
                x = x2
        # kursor
        if not self.scroll and not self.screen.cursor.hidden:
            cx, cy = self.screen.cursor.x, self.screen.cursor.y
            r = QRect(int(ox + cx * self.cw), int(oy + cy * self.ch), int(self.cw), int(self.ch))
            cur = QColor(CURSOR)
            if self.hasFocus():
                if self.blink:
                    cur.setAlpha(200)
                    p.fillRect(r, cur)
                    p.setPen(QColor("white"))
                    p.drawText(r.left(), int(r.top() + self.ascent), self.screen.buffer[cy][cx].data)
            else:
                p.setPen(cur)
                p.drawRect(r.adjusted(0, 0, -1, -1))

    def _blink(self) -> None:
        self.blink = not self.blink
        if self.hasFocus():
            self.update()

    # ------------------------------------------------------------ klawiatura
    def keyPressEvent(self, ev: QKeyEvent) -> None:
        key, mods, text = ev.key(), ev.modifiers(), ev.text()
        ctrl, shift, alt = bool(mods & Qt.ControlModifier), bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier)
        if ctrl and shift and key == Qt.Key_C:
            self.copy()
            return
        if ctrl and shift and key == Qt.Key_V:
            self.paste()
            return
        if shift and key in (Qt.Key_PageUp, Qt.Key_PageDown):
            self.scroll_by(self.rows // 2 if key == Qt.Key_PageUp else -self.rows // 2)
            return
        self.scroll = 0
        self.sel_start = self.sel_end = None
        if key in CURSOR_KEYS:
            app_mode = pyte.modes.DECCKM in self.screen.mode
            letter = CURSOR_KEYS[key]
            if ctrl or shift or alt:
                m = 1 + shift + 2 * alt + 4 * ctrl
                self.write(f"\x1b[1;{m}{letter}".encode())
            else:
                self.write(("\x1bO" if app_mode else "\x1b[") .encode() + letter.encode())
            return
        if key in KEYMAP:
            data = KEYMAP[key]
            if key == Qt.Key_Tab and shift:
                data = b"\x1b[Z"
            self.write((b"\x1b" if alt else b"") + data)
            return
        if ctrl and Qt.Key_A <= key <= Qt.Key_Z:
            self.write(bytes([key - Qt.Key_A + 1]))
            return
        if ctrl and key in (Qt.Key_BracketLeft, Qt.Key_Backslash, Qt.Key_BracketRight, Qt.Key_Space):
            self.write({Qt.Key_BracketLeft: b"\x1b", Qt.Key_Backslash: b"\x1c",
                        Qt.Key_BracketRight: b"\x1d", Qt.Key_Space: b"\x00"}[key])
            return
        if text:
            self.write((b"\x1b" if alt else b"") + text.encode())
            self.blink = True
            return
        super().keyPressEvent(ev)

    def focusNextPrevChild(self, _next: bool) -> bool:
        return False  # Tab trafia do powłoki, nie zmienia fokusu

    # ------------------------------------------------------------ mysz, schowek
    def _cell(self, pos) -> QPoint:
        return QPoint(max(0, min(self.cols - 1, int((pos.x() - 6) // self.cw))),
                      max(0, min(self.rows - 1, int((pos.y() - 4) // self.ch))))

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.sel_start = self.sel_end = self._cell(ev.position())
            self.update()
        elif ev.button() == Qt.MiddleButton:
            text = QGuiApplication.clipboard().text(QGuiApplication.clipboard().Mode.Selection)
            self._paste_text(text)

    def mouseMoveEvent(self, ev) -> None:
        if self.sel_start is not None:
            self.sel_end = self._cell(ev.position())
            self.update()

    def mouseReleaseEvent(self, ev) -> None:
        if self.sel_start and self.sel_end and self.sel_start != self.sel_end:
            QGuiApplication.clipboard().setText(self.selected_text(), QGuiApplication.clipboard().Mode.Selection)

    def mouseDoubleClickEvent(self, ev) -> None:
        c = self._cell(ev.position())
        line = self._visible_lines()[c.y()]
        text = "".join(line[i].data for i in range(self.cols))
        a = b = c.x()
        while a > 0 and not text[a - 1].isspace():
            a -= 1
        while b < self.cols - 1 and not text[b + 1].isspace():
            b += 1
        self.sel_start, self.sel_end = QPoint(a, c.y()), QPoint(b, c.y())
        self.update()

    def wheelEvent(self, ev) -> None:
        steps = ev.angleDelta().y() // 40
        self.scroll_by(steps)

    def scroll_by(self, lines: int) -> None:
        self.scroll = max(0, min(len(self.screen.history.top), self.scroll + lines))
        self.update()

    def selected_text(self) -> str:
        if not self.sel_start or not self.sel_end:
            return ""
        (y1, x1), (y2, x2) = sorted([(self.sel_start.y(), self.sel_start.x()), (self.sel_end.y(), self.sel_end.x())])
        lines = self._visible_lines()
        out = []
        for y in range(y1, y2 + 1):
            a = x1 if y == y1 else 0
            b = x2 if y == y2 else self.cols - 1
            out.append("".join(lines[y][i].data for i in range(a, b + 1)).rstrip())
        return "\n".join(out)

    def copy(self) -> None:
        text = self.selected_text()
        if text:
            QGuiApplication.clipboard().setText(text)

    def paste(self) -> None:
        self._paste_text(QGuiApplication.clipboard().text())

    def _paste_text(self, text: str) -> None:
        if not text:
            return
        data = text.replace("\r\n", "\r").replace("\n", "\r").encode()
        if BRACKETED_PASTE in self.screen.mode:
            data = b"\x1b[200~" + data + b"\x1b[201~"
        self.write(data)
