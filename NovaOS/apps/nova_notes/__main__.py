"""Nova Notes – notatnik z autozapisem, wyszukiwaniem, przypinaniem i podglądem Markdown."""
from __future__ import annotations

import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QPlainTextEdit, QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget)

from novakit import app as novaapp
from novakit.i18n import tr
from novakit.widgets import SearchField, Toast, confirm, flat_button
from nova_notes.storage import Note, NoteStore


class Notes(QMainWindow):
    def __init__(self, store: NoteStore | None = None):
        super().__init__()
        self.setWindowTitle("Nova Notes")
        self.resize(980, 640)
        self.store = store or NoteStore()
        self.current: Note | None = None
        self.dirty = False
        self.loading = False

        split = QSplitter()
        # --- lista notatek
        left = QWidget()
        left.setObjectName("Sidebar")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 10, 10, 10)
        top = QHBoxLayout()
        self.search = SearchField(tr("Search notes…"))
        self.search.textChanged.connect(self.refresh)
        new = flat_button("document-new", tr("New note") + " (Ctrl+N)")
        new.clicked.connect(self.new_note)
        top.addWidget(self.search, 1)
        top.addWidget(new)
        lv.addLayout(top)
        self.list = QListWidget()
        self.list.setObjectName("Sidebar")
        self.list.currentItemChanged.connect(self._select)
        lv.addWidget(self.list, 1)
        self.count = QLabel()
        self.count.setObjectName("Subtitle")
        lv.addWidget(self.count)
        split.addWidget(left)

        # --- edytor
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 12, 16, 12)
        bar = QHBoxLayout()
        self.title = QLabel(tr("No note selected"))
        self.title.setObjectName("Title")
        self.pin = flat_button("pin", tr("Pin"), "window-pin", checkable=True)
        self.pin.toggled.connect(self._pin)
        self.preview_btn = flat_button("view-preview", tr("Markdown preview"), "document-preview", checkable=True)
        self.preview_btn.toggled.connect(self._toggle_preview)
        rename = flat_button("edit-rename", tr("Rename"))
        rename.clicked.connect(self.rename)
        export = flat_button("document-print", tr("Print / export PDF"))
        export.clicked.connect(self.print_note)
        delete = flat_button("edit-delete", tr("Delete"))
        delete.clicked.connect(self.delete)
        bar.addWidget(self.title, 1)
        for b in (self.pin, self.preview_btn, rename, export, delete):
            bar.addWidget(b)
        rv.addLayout(bar)
        self.stack = QStackedWidget()
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(tr("Start typing… (Markdown supported)"))
        f = QFont("Inter")
        f.setPointSize(12)
        self.editor.setFont(f)
        self.editor.textChanged.connect(self._changed)
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.stack.addWidget(self.editor)
        self.stack.addWidget(self.preview)
        rv.addWidget(self.stack, 1)
        self.status = QLabel()
        self.status.setObjectName("Subtitle")
        rv.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([300, 680])
        self.setCentralWidget(split)
        self.toast = Toast(self)

        self.autosave = QTimer(self, singleShot=True, interval=800, timeout=self.save)
        QShortcut(QKeySequence.New, self, activated=self.new_note)
        QShortcut(QKeySequence.Save, self, activated=self.save)
        QShortcut(QKeySequence.Find, self, activated=self.search.setFocus)
        self.refresh()
        if self.list.count():
            self.list.setCurrentRow(0)
        self._enable(self.current is not None)

    def _enable(self, on: bool) -> None:
        for w in (self.editor, self.pin, self.preview_btn):
            w.setEnabled(on)

    def refresh(self) -> None:
        selected = self.current.path if self.current else None
        self.list.blockSignals(True)
        self.list.clear()
        notes = self.store.all(self.search.text())
        for n in notes:
            first = n.read().replace("<!-- pinned -->", "").strip().split("\n", 1)[0][:60]
            item = QListWidgetItem(("📌 " if n.pinned else "") + n.title + ("\n" + first if first else ""))
            item.setData(Qt.UserRole, str(n.path))
            item.setToolTip(time.strftime("%Y-%m-%d %H:%M", time.localtime(n.mtime)))
            self.list.addItem(item)
            if selected and n.path == selected:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self.count.setText(tr("{n} notes", n=len(notes)))

    def _select(self, item: QListWidgetItem | None, _prev=None) -> None:
        if self.dirty:
            self.save()
        if item is None:
            return
        from pathlib import Path
        self.current = Note(Path(item.data(Qt.UserRole)))
        self.loading = True
        text = self.current.read()
        self.pin.blockSignals(True)
        self.pin.setChecked(text.startswith("<!-- pinned -->"))
        self.pin.blockSignals(False)
        self.editor.setPlainText(text.replace("<!-- pinned -->\n", "", 1))
        self.loading = False
        self.title.setText(self.current.title)
        self._enable(True)
        self._update_preview()
        self._status()

    def _changed(self) -> None:
        if self.loading or not self.current:
            return
        self.dirty = True
        self.status.setText(tr("Editing…"))
        self.autosave.start()

    def save(self) -> None:
        if not self.current or not self.dirty:
            return
        prefix = "<!-- pinned -->\n" if self.pin.isChecked() else ""
        self.store.save(self.current, prefix + self.editor.toPlainText())
        self.dirty = False
        self._status(tr("Saved"))
        self._update_preview()

    def _status(self, extra: str = "") -> None:
        text = self.editor.toPlainText()
        words = len(text.split())
        msg = tr("{w} words · {c} characters", w=words, c=len(text))
        self.status.setText(f"{msg}   {extra}")

    def new_note(self) -> None:
        self.save()
        self.current = self.store.create()
        self.search.clear()
        self.refresh()
        self._select(self.list.currentItem())
        self.editor.setFocus()

    def rename(self) -> None:
        if not self.current:
            return
        name, ok = QInputDialog.getText(self, tr("Rename"), tr("New name:"), text=self.current.title)
        if ok and name.strip():
            self.save()
            self.current = self.store.rename(self.current, name.strip())
            self.title.setText(self.current.title)
            self.refresh()

    def delete(self) -> None:
        if not self.current:
            return
        if confirm(self, tr("Delete note"), tr("Move “{t}” to trash?", t=self.current.title), danger=True,
                   yes=tr("Delete")):
            self.store.delete(self.current)
            self.current = None
            self.dirty = False
            self.loading = True
            self.editor.clear()
            self.loading = False
            self.title.setText(tr("No note selected"))
            self._enable(False)
            self.refresh()
            self.toast.show_message(tr("Moved to trash"))

    def _pin(self, on: bool) -> None:
        if self.current:
            self.dirty = True
            self.save()
            self.refresh()

    def _toggle_preview(self, on: bool) -> None:
        self._update_preview()
        self.stack.setCurrentIndex(1 if on else 0)

    def _update_preview(self) -> None:
        doc = QTextDocument()
        doc.setMarkdown(self.editor.toPlainText())
        self.preview.setHtml(doc.toHtml())

    def print_note(self) -> None:
        if not self.current:
            return
        printer = QPrinter(QPrinter.HighResolution)
        if QPrintDialog(printer, self).exec():
            doc = QTextDocument()
            doc.setMarkdown(self.editor.toPlainText())
            doc.print_(printer)

    def closeEvent(self, ev) -> None:
        self.save()
        super().closeEvent(ev)


def main() -> int:
    return novaapp.run(Notes, "nova-notes", "Nova Notes")


if __name__ == "__main__":
    sys.exit(main())
