"""Nova Settings – ustawienia systemu NovaOS."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from novakit import app as novaapp
from novakit.i18n import tr
from novakit.widgets import SearchField, Sidebar, Toast
from nova_settings.pages import ALL_PAGES


class Settings(QMainWindow):
    def __init__(self, start: str | None = None):
        super().__init__()
        self.setWindowTitle("Nova Settings")
        self.resize(1080, 720)
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        left = QWidget()
        left.setObjectName("Sidebar")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 10, 0, 8)
        self.search = SearchField(tr("Search settings…"))
        self.search.textChanged.connect(self._filter)
        self.side = Sidebar(240)
        lv.addWidget(self.search)
        lv.addWidget(self.side, 1)
        h.addWidget(left)
        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.toast = Toast(self)
        self.pages: dict[int, QWidget] = {}
        for i, cls in enumerate(ALL_PAGES):
            self.side.add(tr(cls.TITLE), cls.ICON, "preferences-system", data=i)
            self.stack.addWidget(QWidget())  # leniwe tworzenie stron
        self.side.currentRowChanged.connect(self.open_page)
        names = [c.__name__.replace("Page", "").lower() for c in ALL_PAGES]
        self.side.setCurrentRow(names.index(start) if start in names else 0)

    def open_page(self, i: int) -> None:
        if i < 0:
            return
        if i not in self.pages:
            page = ALL_PAGES[i](self)
            self.pages[i] = page
            old = self.stack.widget(i)
            self.stack.removeWidget(old)
            self.stack.insertWidget(i, page)
            old.deleteLater()
        self.stack.setCurrentIndex(i)
        self.pages[i].refresh()

    def _filter(self, text: str) -> None:
        t = text.lower()
        for r in range(self.side.count()):
            it = self.side.item(r)
            cls = ALL_PAGES[it.data(Qt.UserRole)]
            hay = (it.text() + " " + tr(cls.SUBTITLE) + " " + cls.TITLE + " " + cls.SUBTITLE).lower()
            it.setHidden(bool(t) and t not in hay)


def main() -> int:
    start = sys.argv[1] if len(sys.argv) > 1 else None
    return novaapp.run(lambda: Settings(start), "nova-settings", "Nova Settings")


if __name__ == "__main__":
    sys.exit(main())
