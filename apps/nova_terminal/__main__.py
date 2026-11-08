"""Nova Terminal – terminal z kartami, schowkiem, przewijaniem historii i zoomem."""
from __future__ import annotations

import argparse
import sys

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QMenu, QTabWidget, QToolButton

from novakit import app as novaapp
from novakit.config import Store
from novakit.i18n import tr
from novakit.widgets import icon
from nova_terminal.term import TerminalWidget


class Terminal(QMainWindow):
    def __init__(self, workdir: str | None = None, command: list[str] | None = None):
        super().__init__()
        self.setWindowTitle("Nova Terminal")
        self.resize(900, 560)
        self.store = Store("terminal", {"font_size": 11})
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._focus)
        plus = QToolButton()
        plus.setIcon(icon("tab-new", "list-add"))
        plus.setToolTip(tr("New tab") + " (Ctrl+Shift+T)")
        plus.setAutoRaise(True)
        plus.clicked.connect(lambda: self.new_tab())
        menu_btn = QToolButton()
        menu_btn.setIcon(icon("application-menu", "open-menu"))
        menu_btn.setAutoRaise(True)
        menu_btn.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(menu_btn)
        m.addAction(tr("Copy") + "\tCtrl+Shift+C", lambda: self.term().copy())
        m.addAction(tr("Paste") + "\tCtrl+Shift+V", lambda: self.term().paste())
        m.addSeparator()
        m.addAction(tr("Zoom in") + "\tCtrl++", lambda: self.zoom(1))
        m.addAction(tr("Zoom out") + "\tCtrl+-", lambda: self.zoom(-1))
        m.addAction(tr("Reset zoom") + "\tCtrl+0", lambda: self.zoom(0))
        menu_btn.setMenu(m)
        self.tabs.setCornerWidget(plus)
        self.tabs.setCornerWidget(menu_btn, corner=__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.TopLeftCorner)
        self.setCentralWidget(self.tabs)
        for seq, fn in [("Ctrl+Shift+T", lambda: self.new_tab(self.term().cwd() if self.term() else None)),
                        ("Ctrl+Shift+W", lambda: self.close_tab(self.tabs.currentIndex())),
                        ("Ctrl++", lambda: self.zoom(1)), ("Ctrl+=", lambda: self.zoom(1)),
                        ("Ctrl+-", lambda: self.zoom(-1)), ("Ctrl+0", lambda: self.zoom(0)),
                        ("Ctrl+PgDown", lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())),
                        ("Ctrl+PgUp", lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % self.tabs.count()))]:
            QShortcut(QKeySequence(seq), self, activated=fn)
        self.new_tab(workdir, command)

    def term(self) -> TerminalWidget | None:
        return self.tabs.currentWidget()

    def new_tab(self, cwd: str | None = None, command: list[str] | None = None) -> None:
        t = TerminalWidget(cwd, command, self.store.get("font_size", 11))
        idx = self.tabs.addTab(t, "Terminal")
        t.title_changed.connect(lambda title, w=t: self._title(w, title))
        t.closed.connect(lambda w=t: self.close_tab(self.tabs.indexOf(w)))
        self.tabs.setCurrentIndex(idx)
        self.tabs.setTabBarAutoHide(True)
        t.setFocus()

    def _title(self, w: TerminalWidget, title: str) -> None:
        i = self.tabs.indexOf(w)
        if i >= 0:
            self.tabs.setTabText(i, (title or "Terminal")[:40])
            if w is self.term():
                self.setWindowTitle(f"{title} — Nova Terminal" if title else "Nova Terminal")

    def _focus(self, _i: int) -> None:
        if self.term():
            self.term().setFocus()

    def close_tab(self, index: int) -> None:
        if index < 0:
            return
        w = self.tabs.widget(index)
        w.terminate()
        self.tabs.removeTab(index)
        w.deleteLater()
        if self.tabs.count() == 0:
            self.close()

    def zoom(self, delta: int) -> None:
        size = 11 if delta == 0 else self.store.get("font_size", 11) + delta
        size = max(6, min(size, 40))
        self.store.set("font_size", size)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_font_size(size)

    def closeEvent(self, ev) -> None:
        for i in range(self.tabs.count()):
            self.tabs.widget(i).terminate()
        super().closeEvent(ev)


def main() -> int:
    ap = argparse.ArgumentParser(prog="nova-terminal")
    ap.add_argument("--workdir", "-w")
    ap.add_argument("-e", "--execute", nargs=argparse.REMAINDER)
    args, _ = ap.parse_known_args()
    return novaapp.run(lambda: Terminal(args.workdir, args.execute or None), "nova-terminal", "Nova Terminal")


if __name__ == "__main__":
    sys.exit(main())
