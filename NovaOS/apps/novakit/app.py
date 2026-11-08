"""Uruchamianie aplikacji Nova ze wspólnym motywem i ikoną."""
from __future__ import annotations

import signal
import sys
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget

from . import theme
from .widgets import icon


def run(factory: Callable[[], QWidget], app_id: str, name: str) -> int:
    QApplication.setApplicationName(name)
    QApplication.setOrganizationName("NovaOS")
    QApplication.setDesktopFileName(app_id)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    if QIcon.themeName() in ("", "hicolor"):
        QIcon.setThemeName("Papirus-Dark" if theme.is_dark(app.palette()) else "Papirus")
        QIcon.setFallbackThemeName("breeze")
    app.setWindowIcon(icon(app_id, "novaos-logo"))
    theme.apply(app)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    window = factory()
    window.show()
    return app.exec()
