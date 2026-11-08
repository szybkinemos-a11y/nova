"""Wspólne widżety NovaOS."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QToolButton, QVBoxLayout, QWidget)

from .i18n import tr

_ICON_DIRS = [Path("/usr/share/icons/hicolor/scalable/apps"),
              Path(__file__).resolve().parent.parent.parent / "branding-out" / "icons" / "hicolor" / "scalable" / "apps"]


def icon(name: str, *fallbacks: str) -> QIcon:
    """Ikona z motywu systemowego, z kolejnymi zamiennikami."""
    for n in (name, *fallbacks):
        ic = QIcon.fromTheme(n)
        if not ic.isNull():
            return ic
    for d in _ICON_DIRS:
        p = d / f"{name}.svg"
        if p.is_file():
            return QIcon(str(p))
    return QIcon()


def card(layout=None) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    if layout is not None:
        frame.setLayout(layout)
        layout.setContentsMargins(16, 14, 16, 14)
    return frame


def title(text: str, subtitle: str | None = None) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 6)
    lay.setSpacing(2)
    t = QLabel(text)
    t.setObjectName("Title")
    lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("Subtitle")
        s.setWordWrap(True)
        lay.addWidget(s)
    return w


def section(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Section")
    return lbl


def flat_button(icon_name: str, tooltip: str, *fallbacks: str, checkable: bool = False) -> QToolButton:
    b = QToolButton()
    b.setObjectName("Flat")
    b.setIcon(icon(icon_name, *fallbacks))
    b.setIconSize(QSize(20, 20))
    b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setAutoRaise(True)
    return b


class SearchField(QLineEdit):
    def __init__(self, placeholder: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Search")
        self.setPlaceholderText(placeholder or tr("Search…"))
        self.setClearButtonEnabled(True)
        ic = icon("search", "edit-find")
        if not ic.isNull():
            self.addAction(ic, QLineEdit.LeadingPosition)


class Sidebar(QListWidget):
    """Panel nawigacji po lewej stronie (ikony + etykiety)."""

    def __init__(self, width: int = 220, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(width)
        self.setIconSize(QSize(20, 20))
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def add(self, text: str, icon_name: str, *fallbacks: str, data=None) -> QListWidgetItem:
        item = QListWidgetItem(icon(icon_name, *fallbacks), text)
        item.setData(Qt.UserRole, data if data is not None else text)
        self.addItem(item)
        return item


class Toast(QLabel):
    """Krótki komunikat wyświetlany na dole okna."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._timer = QTimer(self, singleShot=True, timeout=self._fade_out)

    def show_message(self, text: str, msec: int = 2800) -> None:
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 28)
        self.raise_()
        self.show()
        self._anim.stop()
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(msec)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(350)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.hide)
        self._anim.start()


def confirm(parent: QWidget | None, title_text: str, text: str, danger: bool = False,
            yes: str | None = None) -> bool:
    """Okno potwierdzenia. Domyślny przycisk to zawsze 'Anuluj' (bezpieczny)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    box.setWindowTitle(title_text)
    box.setText(text)
    ok = box.addButton(yes or tr("Continue"), QMessageBox.AcceptRole)
    cancel = box.addButton(tr("Cancel"), QMessageBox.RejectRole)
    if danger:
        ok.setObjectName("Danger")
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is ok


def notify(summary: str, body: str = "", icon_name: str = "novaos-logo", app_name: str = "NovaOS") -> None:
    """Powiadomienie systemowe (org.freedesktop.Notifications)."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface  # type: ignore
        iface = QDBusInterface("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                               "org.freedesktop.Notifications", QDBusConnection.sessionBus())
        if iface.isValid():
            iface.call("Notify", app_name, 0, icon_name, summary, body, [], {}, 5000)
            return
    except Exception:  # noqa: BLE001 – QtDBus może być niedostępne
        pass
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", app_name, "-i", icon_name, summary, body])


def hbox(*widgets, spacing: int = 8, margins=(0, 0, 0, 0), stretch_last: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    if stretch_last:
        lay.addStretch(1)
    return lay
