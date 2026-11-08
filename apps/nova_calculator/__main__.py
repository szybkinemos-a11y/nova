"""Nova Calculator – kalkulator standardowy i naukowy z historią."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QMainWindow, QPushButton, QRadioButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from novakit import app as novaapp
from novakit.i18n import tr
from novakit.config import Store
from nova_calculator.engine import CalcError, Engine, fmt

STANDARD = [["C", "(", ")", "÷"], ["7", "8", "9", "×"], ["4", "5", "6", "−"],
            ["1", "2", "3", "+"], ["%", "0", ".", "="]]
SCIENTIFIC = [["sin", "cos", "tan", "π"], ["asin", "acos", "atan", "e"],
              ["√", "^", "!", "ln"], ["log", "ans", "⌫", "mod"]]


class Calculator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova Calculator")
        self.resize(720, 560)
        self.engine = Engine()
        self.store = Store("calculator", {"history": [], "scientific": True})
        self.just_evaluated = False

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        split = QSplitter()
        root.addWidget(split)

        # --- lewa strona: wyświetlacz + klawiatura
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        self.expr = QLabel("")
        self.expr.setAlignment(Qt.AlignRight)
        self.expr.setObjectName("Subtitle")
        self.expr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.display = QLabel("0")
        self.display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f = QFont()
        f.setPointSize(30)
        f.setWeight(QFont.Light)
        self.display.setFont(f)
        self.display.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.display.setMinimumHeight(64)
        lv.addWidget(self.expr)
        lv.addWidget(self.display)

        modes = QHBoxLayout()
        self.sci_toggle = QPushButton(tr("Scientific"))
        self.sci_toggle.setCheckable(True)
        self.sci_toggle.setChecked(self.store.get("scientific", True))
        self.sci_toggle.toggled.connect(self._toggle_sci)
        self.deg = QRadioButton("DEG")
        self.rad = QRadioButton("RAD")
        self.deg.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.deg)
        grp.addButton(self.rad)
        self.deg.toggled.connect(lambda on: setattr(self.engine, "degrees", on))
        modes.addWidget(self.sci_toggle)
        modes.addStretch(1)
        modes.addWidget(self.deg)
        modes.addWidget(self.rad)
        lv.addLayout(modes)

        self.sci_panel = QWidget()
        self.sci_panel.setLayout(self._grid(SCIENTIFIC, small=True))
        lv.addWidget(self.sci_panel)
        lv.addLayout(self._grid(STANDARD), 1)
        split.addWidget(left)

        # --- prawa strona: historia
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        hl = QLabel(tr("History"))
        hl.setObjectName("Section")
        self.history = QListWidget()
        self.history.itemClicked.connect(lambda it: self._set_input(it.data(Qt.UserRole)))
        clear = QPushButton(tr("Clear history"))
        clear.clicked.connect(self._clear_history)
        rv.addWidget(hl)
        rv.addWidget(self.history, 1)
        rv.addWidget(clear)
        split.addWidget(right)
        split.setSizes([480, 220])
        self.setCentralWidget(central)

        for entry in self.store.get("history", [])[-50:]:
            self._add_history(entry["expr"], entry["result"], save=False)
        self._toggle_sci(self.sci_toggle.isChecked())
        QShortcut(QKeySequence.Copy, self, activated=lambda: QApplication.clipboard().setText(self.display.text()))
        QShortcut(QKeySequence.Paste, self, activated=lambda: self._append(QApplication.clipboard().text()))
        self.input = ""

    def _grid(self, rows, small=False) -> QGridLayout:
        g = QGridLayout()
        g.setSpacing(8)
        for r, row in enumerate(rows):
            for c, key in enumerate(row):
                b = QPushButton(key)
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                b.setMinimumHeight(38 if small else 54)
                b.setFocusPolicy(Qt.NoFocus)
                if key == "=":
                    b.setObjectName("Accent")
                font = b.font()
                font.setPointSize(11 if small else 15)
                b.setFont(font)
                b.clicked.connect(lambda _=False, k=key: self.press(k))
                g.addWidget(b, r, c)
        return g

    def _toggle_sci(self, on: bool) -> None:
        self.sci_panel.setVisible(on)
        self.deg.setVisible(on)
        self.rad.setVisible(on)
        self.store.set("scientific", on)

    # --- logika klawiszy
    def press(self, key: str) -> None:
        if key == "C":
            self.input = ""
            self.expr.setText("")
            self._show("0")
        elif key == "⌫":
            self.input = self.input[:-1]
            self._show(self.input or "0")
        elif key == "=":
            self._evaluate()
        elif key in ("sin", "cos", "tan", "asin", "acos", "atan", "ln", "log"):
            self._append(key + "(")
        elif key == "√":
            self._append("√(")
        elif key == "mod":
            self._append(" mod ")
        else:
            self._append(key)

    def _append(self, text: str) -> None:
        if self.just_evaluated:
            # operator po "=" kontynuuje od wyniku, cokolwiek innego zaczyna nowe wyrażenie
            self.input = "ans" if text.strip() and text.strip()[0] in "+−×÷^!%m" else ""
        self.just_evaluated = False
        self.input += text
        self._show(self.input)

    def _set_input(self, text: str) -> None:
        self.input = text
        self.just_evaluated = False
        self._show(text)

    def _show(self, text: str) -> None:
        self.display.setText(text)

    def _evaluate(self) -> None:
        if not self.input:
            return
        try:
            value = self.engine.evaluate(self.input)
        except CalcError:
            self.expr.setText(self.input)
            self._show(tr("Error"))
            self.input = ""
            return
        result = fmt(value)
        self.expr.setText(self.input + " =")
        self._show(result)
        self._add_history(self.input, result)
        self.input = ""
        self.just_evaluated = True

    def _add_history(self, expr: str, result: str, save: bool = True) -> None:
        self.history.insertItem(0, f"{expr} = {result}")
        self.history.item(0).setData(Qt.UserRole, expr)
        if save:
            hist = self.store.get("history", [])
            hist.append({"expr": expr, "result": result})
            self.store.set("history", hist[-100:])

    def _clear_history(self) -> None:
        self.history.clear()
        self.store.set("history", [])

    def keyPressEvent(self, ev) -> None:
        k, t = ev.key(), ev.text()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.press("=")
        elif k == Qt.Key_Backspace:
            self.press("⌫")
        elif k == Qt.Key_Escape:
            self.press("C")
        elif t and t in "0123456789.,+-*/()%^!":
            self._append({"*": "×", "/": "÷", "-": "−", ",": "."}.get(t, t))
        else:
            super().keyPressEvent(ev)


def main() -> int:
    return novaapp.run(Calculator, "nova-calculator", "Nova Calculator")


if __name__ == "__main__":
    sys.exit(main())
