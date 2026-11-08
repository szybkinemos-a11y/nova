"""Spójny wygląd aplikacji Nova.

W sesji KDE Plasma kolory pochodzą ze schematu systemowego (Nova Dark/Light),
a tu dokładamy tylko zaokrąglenia, panel boczny, karty i akcent. Poza KDE
(np. testy) ustawiamy styl Fusion i własną paletę Nova.
"""
from __future__ import annotations

import os

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = QColor("#7B61FF")
VIOLET = QColor("#A855F7")
BLUE = QColor("#3B82F6")


def under_kde() -> bool:
    return "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def is_dark(palette: QPalette | None = None) -> bool:
    pal = palette or QApplication.palette()
    return pal.color(QPalette.Window).lightness() < 128


def nova_palette(dark: bool = True) -> QPalette:
    p = QPalette()
    if dark:
        c = dict(window="#15131F", base="#0F0D17", alt="#1B1828", text="#ECEBF5", button="#221F33",
                 mid="#2A2640", tip="#1E1B2E", dis="#6B6782")
    else:
        c = dict(window="#F4F3FA", base="#FFFFFF", alt="#F7F6FC", text="#1C1A2B", button="#ECEAF7",
                 mid="#D9D6EA", tip="#FFFFFF", dis="#9C98B3")
    p.setColor(QPalette.Window, QColor(c["window"]))
    p.setColor(QPalette.WindowText, QColor(c["text"]))
    p.setColor(QPalette.Base, QColor(c["base"]))
    p.setColor(QPalette.AlternateBase, QColor(c["alt"]))
    p.setColor(QPalette.Text, QColor(c["text"]))
    p.setColor(QPalette.Button, QColor(c["button"]))
    p.setColor(QPalette.ButtonText, QColor(c["text"]))
    p.setColor(QPalette.Mid, QColor(c["mid"]))
    p.setColor(QPalette.ToolTipBase, QColor(c["tip"]))
    p.setColor(QPalette.ToolTipText, QColor(c["text"]))
    p.setColor(QPalette.PlaceholderText, QColor(c["dis"]))
    p.setColor(QPalette.Highlight, ACCENT)
    p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.Link, QColor("#8AB4FF" if dark else "#2563EB"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["dis"]))
    return p


def _rgba(color: QColor, alpha: float) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{alpha:.2f})"


def stylesheet(palette: QPalette) -> str:
    acc = palette.color(QPalette.Highlight)
    text = palette.color(QPalette.WindowText)
    window = palette.color(QPalette.Window)
    base = palette.color(QPalette.Base)
    side = window.darker(112) if is_dark(palette) else window.darker(104)
    return f"""
    QWidget#Sidebar, QListWidget#Sidebar {{
        background: {side.name()}; border: none; padding: 8px; outline: 0;
    }}
    QListWidget#Sidebar::item {{
        padding: 9px 12px; margin: 2px 0; border-radius: 10px; color: {text.name()};
    }}
    QListWidget#Sidebar::item:hover {{ background: {_rgba(text, 0.07)}; }}
    QListWidget#Sidebar::item:selected {{ background: {_rgba(acc, 0.85)}; color: white; }}
    QLabel#Title {{ font-size: 20pt; font-weight: 700; }}
    QLabel#Subtitle {{ color: {_rgba(text, 0.65)}; }}
    QLabel#Section {{ font-size: 12pt; font-weight: 600; margin-top: 8px; }}
    QFrame#Card {{
        background: {_rgba(text, 0.045)}; border: 1px solid {_rgba(text, 0.09)}; border-radius: 14px;
    }}
    QLineEdit#Search, QLineEdit#UrlBar {{
        border: 1px solid {_rgba(text, 0.14)}; border-radius: 17px; padding: 6px 14px;
        background: {base.name()}; min-height: 22px;
    }}
    QLineEdit#Search:focus, QLineEdit#UrlBar:focus {{ border: 2px solid {acc.name()}; }}
    QPushButton#Accent {{
        background: {acc.name()}; color: white; border: none; border-radius: 10px; padding: 7px 18px; font-weight: 600;
    }}
    QPushButton#Accent:hover {{ background: {acc.lighter(115).name()}; }}
    QPushButton#Accent:disabled {{ background: {_rgba(acc, 0.4)}; }}
    QPushButton#Danger {{
        background: #DC2626; color: white; border: none; border-radius: 10px; padding: 7px 18px; font-weight: 600;
    }}
    QToolButton#Flat {{ border: none; border-radius: 9px; padding: 6px; }}
    QToolButton#Flat:hover {{ background: {_rgba(text, 0.09)}; }}
    QToolButton#Flat:checked {{ background: {_rgba(acc, 0.25)}; }}
    QProgressBar {{ border: none; border-radius: 4px; background: {_rgba(text, 0.1)}; max-height: 8px; text-align: center; }}
    QProgressBar::chunk {{ border-radius: 4px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {VIOLET.name()}, stop:1 {BLUE.name()}); }}
    QLabel#Toast {{
        background: {_rgba(window.darker(130) if is_dark(palette) else QColor('#1C1A2B'), 0.95)}; color: white;
        border-radius: 12px; padding: 10px 18px;
    }}
    """


def apply(app: QApplication) -> None:
    if not under_kde() or os.environ.get("NOVAOS_FORCE_PALETTE"):
        app.setStyle("Fusion")
        dark = os.environ.get("NOVAOS_THEME", "dark") != "light"
        app.setPalette(nova_palette(dark))
    app.setStyleSheet(stylesheet(app.palette()))
