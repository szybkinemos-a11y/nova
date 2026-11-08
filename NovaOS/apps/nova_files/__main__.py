"""Nova Files – menedżer plików: miejsca, dyski, widok ikon/listy, kopiuj/wytnij/wklej, kosz."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QDir, QFileInfo, QModelIndex, QSize, QSortFilterProxyModel, QStorageInfo, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileSystemModel, QFormLayout, QDialog,
                               QDialogButtonBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QListView, QMainWindow, QMenu, QProgressBar, QSplitter, QStackedWidget,
                               QTreeView, QVBoxLayout, QWidget)

from novakit import app as novaapp
from novakit.config import Store, user_dir
from novakit.i18n import tr
from novakit.widgets import SearchField, Sidebar, Toast, confirm, flat_button, icon
from nova_files.ops import dir_size, start_transfer

TRASH = Path.home() / ".local/share/Trash/files"


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class Proxy(QSortFilterProxyModel):
    """Foldery zawsze na górze, filtr nazw."""

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        m = self.sourceModel()
        ld, rd = m.isDir(left), m.isDir(right)
        if ld != rd:
            return ld if self.sortOrder() == Qt.AscendingOrder else rd
        if left.column() == 0:
            return m.fileName(left).lower() < m.fileName(right).lower()
        return super().lessThan(left, right)

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        pattern = self.filterRegularExpression().pattern()
        if not pattern:
            return True
        m = self.sourceModel()
        idx = m.index(row, 0, parent)
        if m.filePath(idx) == getattr(self, "root_path", None) or not parent.isValid():
            return True
        if m.filePath(parent) != getattr(self, "root_path", None):
            return True
        return pattern.lower() in m.fileName(idx).lower()


class Files(QMainWindow):
    def __init__(self, start: str | None = None):
        super().__init__()
        self.setWindowTitle("Nova Files")
        self.resize(1100, 680)
        self.store = Store("files", {"view": "icons", "hidden": False})
        self.history: list[str] = []
        self.forward: list[str] = []
        self.clipboard: tuple[list[Path], bool] = ([], False)  # (pliki, czy wycinanie)
        self.threads = []

        self.model = QFileSystemModel(self)
        self.model.setRootPath("/")
        self.model.setReadOnly(False)
        self._apply_hidden(self.store.get("hidden"))
        self.proxy = Proxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setDynamicSortFilter(True)
        self.proxy.sort(0, Qt.AscendingOrder)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- pasek narzędzi
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 8, 10, 8)
        self.back_btn = flat_button("go-previous", tr("Back") + " (Alt+←)")
        self.fwd_btn = flat_button("go-next", tr("Forward") + " (Alt+→)")
        up = flat_button("go-up", tr("Parent folder") + " (Alt+↑)")
        self.back_btn.clicked.connect(self.go_back)
        self.fwd_btn.clicked.connect(self.go_forward)
        up.clicked.connect(self.go_up)
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("UrlBar")
        self.path_edit.returnPressed.connect(lambda: self.navigate(os.path.expanduser(self.path_edit.text())))
        self.search = SearchField(tr("Filter this folder…"))
        self.search.setMaximumWidth(260)
        self.search.textChanged.connect(self._filter)
        newdir = flat_button("folder-new", tr("New folder") + " (Ctrl+Shift+N)")
        newdir.clicked.connect(self.new_folder)
        self.view_btn = flat_button("view-list-details", tr("Toggle list / icons"), checkable=True)
        self.view_btn.setChecked(self.store.get("view") == "list")
        self.view_btn.toggled.connect(self._set_view)
        hidden = flat_button("view-hidden", tr("Show hidden files") + " (Ctrl+H)", checkable=True)
        hidden.setChecked(self.store.get("hidden"))
        hidden.toggled.connect(self._toggle_hidden)
        self.hidden_btn = hidden
        term = flat_button("utilities-terminal", tr("Open terminal here"), "nova-terminal")
        term.clicked.connect(self.open_terminal)
        for w in (self.back_btn, self.fwd_btn, up):
            bar.addWidget(w)
        bar.addWidget(self.path_edit, 1)
        bar.addWidget(self.search)
        for w in (newdir, self.view_btn, hidden, term):
            bar.addWidget(w)
        root.addLayout(bar)

        split = QSplitter()
        # --- panel boczny: miejsca + dyski
        self.side = Sidebar(210)
        self.side.itemClicked.connect(lambda it: self.navigate(it.data(Qt.UserRole)))
        split.addWidget(self.side)
        self._fill_sidebar()

        # --- widoki
        self.stack = QStackedWidget()
        self.icons = QListView()
        self.icons.setViewMode(QListView.IconMode)
        self.icons.setResizeMode(QListView.Adjust)
        self.icons.setIconSize(QSize(56, 56))
        self.icons.setGridSize(QSize(112, 100))
        self.icons.setWordWrap(True)
        self.icons.setUniformItemSizes(True)
        self.icons.setMovement(QListView.Static)
        self.list = QTreeView()
        self.list.setRootIsDecorated(False)
        self.list.setSortingEnabled(True)
        self.list.setAlternatingRowColors(True)
        for v in (self.icons, self.list):
            v.setModel(self.proxy)
            v.setSelectionMode(QAbstractItemView.ExtendedSelection)
            v.setEditTriggers(QAbstractItemView.EditKeyPressed)
            v.setDragDropMode(QAbstractItemView.DragDrop)
            v.setDefaultDropAction(Qt.MoveAction)
            v.doubleClicked.connect(self.activate)
            v.setContextMenuPolicy(Qt.CustomContextMenu)
            v.customContextMenuRequested.connect(self._menu)
        self.list.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.stack.addWidget(self.icons)
        self.stack.addWidget(self.list)
        split.addWidget(self.stack)
        split.setStretchFactor(1, 1)
        root.addWidget(split, 1)

        # --- pasek stanu
        st = QHBoxLayout()
        st.setContentsMargins(12, 4, 12, 6)
        self.status = QLabel()
        self.status.setObjectName("Subtitle")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        st.addWidget(self.status, 1)
        st.addWidget(self.progress)
        root.addLayout(st)
        self.setCentralWidget(central)
        self.toast = Toast(self)

        self._set_view(self.view_btn.isChecked())
        self._shortcuts()
        self.model.directoryLoaded.connect(lambda _p: self._update_status())
        self.navigate(start or str(Path.home()), record=False)

    # ------------------------------------------------------------ nawigacja
    def _fill_sidebar(self) -> None:
        self.side.clear()
        places = [(tr("Home"), Path.home(), "user-home"),
                  (tr("Desktop"), user_dir("DESKTOP", "Desktop"), "user-desktop"),
                  (tr("Documents"), user_dir("DOCUMENTS", "Documents"), "folder-documents"),
                  (tr("Downloads"), user_dir("DOWNLOAD", "Downloads"), "folder-download"),
                  (tr("Music"), user_dir("MUSIC", "Music"), "folder-music"),
                  (tr("Pictures"), user_dir("PICTURES", "Pictures"), "folder-pictures"),
                  (tr("Videos"), user_dir("VIDEOS", "Videos"), "folder-videos"),
                  (tr("Trash"), TRASH, "user-trash")]
        for name, path, ic in places:
            if path.exists() or path == TRASH:
                self.side.add(name, ic, "folder", data=str(path))
        sep = self.side.add(tr("Devices"), "", data="")
        sep.setFlags(Qt.NoItemFlags)
        self.side.add(tr("Computer") + " (/)", "drive-harddisk", "folder", data="/")
        for vol in QStorageInfo.mountedVolumes():
            rp = vol.rootPath()
            if vol.isValid() and vol.isReady() and rp.startswith(("/media", "/run/media", "/mnt")):
                label = vol.displayName() or rp
                self.side.add(label, "drive-removable-media", "drive-harddisk", data=rp)

    def current(self) -> str:
        return self.model.filePath(self.proxy.mapToSource(self.icons.rootIndex())) or "/"

    def navigate(self, path: str, record: bool = True) -> None:
        p = Path(path)
        if p == TRASH:
            TRASH.mkdir(parents=True, exist_ok=True)
        if not p.is_dir():
            self.toast.show_message(tr("Folder does not exist: {p}", p=path))
            self.path_edit.setText(self.current())
            return
        if not os.access(p, os.R_OK | os.X_OK):
            self.toast.show_message(tr("Permission denied: {p}", p=path))
            return
        if record and self.current() != str(p):
            self.history.append(self.current())
            self.forward.clear()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.proxy.root_path = str(p)
        self.proxy.setFilterFixedString("")
        src = self.model.setRootPath(str(p))
        idx = self.proxy.mapFromSource(src)
        self.icons.setRootIndex(idx)
        self.list.setRootIndex(idx)
        self.path_edit.setText(str(p))
        self.setWindowTitle(f"{p.name or '/'} — Nova Files")
        self.back_btn.setEnabled(bool(self.history))
        self.fwd_btn.setEnabled(bool(self.forward))
        self._update_status()

    def go_back(self) -> None:
        if self.history:
            self.forward.append(self.current())
            self.navigate(self.history.pop(), record=False)

    def go_forward(self) -> None:
        if self.forward:
            self.history.append(self.current())
            self.navigate(self.forward.pop(), record=False)

    def go_up(self) -> None:
        parent = str(Path(self.current()).parent)
        if parent != self.current():
            self.navigate(parent)

    def activate(self, idx: QModelIndex) -> None:
        path = self.model.filePath(self.proxy.mapToSource(idx))
        if os.path.isdir(path):
            self.navigate(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ------------------------------------------------------------ widok
    def _view(self):
        return self.stack.currentWidget()

    def _set_view(self, as_list: bool) -> None:
        self.stack.setCurrentIndex(1 if as_list else 0)
        self.store.set("view", "list" if as_list else "icons")

    def _apply_hidden(self, show: bool) -> None:
        flt = QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs
        if show:
            flt |= QDir.Hidden
        self.model.setFilter(flt)

    def _toggle_hidden(self, show: bool) -> None:
        self._apply_hidden(show)
        self.store.set("hidden", show)

    def _filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)
        self.icons.setRootIndex(self.proxy.mapFromSource(self.model.index(self.proxy.root_path)))
        self.list.setRootIndex(self.icons.rootIndex())

    def selected(self) -> list[Path]:
        rows = self._view().selectionModel().selectedIndexes()
        paths = {self.model.filePath(self.proxy.mapToSource(i)) for i in rows if i.column() == 0}
        return [Path(p) for p in sorted(paths)]

    def _update_status(self) -> None:
        root = self.icons.rootIndex()
        n = self.proxy.rowCount(root)
        free = QStorageInfo(self.current()).bytesAvailable()
        sel = self.selected() if self._view().selectionModel() else []
        text = tr("{n} items", n=n)
        if sel:
            text += " · " + tr("{s} selected", s=len(sel))
        if free > 0:
            text += " · " + tr("{f} free", f=human(free))
        self.status.setText(text)

    # ------------------------------------------------------------ operacje
    def new_folder(self) -> None:
        name, ok = QInputDialog.getText(self, tr("New folder"), tr("Folder name:"), text=tr("New folder"))
        if ok and name.strip():
            try:
                (Path(self.current()) / name.strip()).mkdir()
            except OSError as exc:
                self.toast.show_message(str(exc))

    def rename(self) -> None:
        sel = self.selected()
        if len(sel) == 1:
            idx = self.proxy.mapFromSource(self.model.index(str(sel[0])))
            self._view().edit(idx)

    def copy(self, cut: bool = False) -> None:
        sel = self.selected()
        if sel:
            self.clipboard = (sel, cut)
            from PySide6.QtCore import QMimeData
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(p)) for p in sel])
            QApplication.clipboard().setMimeData(mime)
            self.toast.show_message(tr("{n} items cut", n=len(sel)) if cut else tr("{n} items copied", n=len(sel)))

    def paste(self) -> None:
        files, cut = self.clipboard
        if not files:
            urls = QApplication.clipboard().mimeData().urls()
            files, cut = [Path(u.toLocalFile()) for u in urls if u.isLocalFile()], False
        files = [f for f in files if f.exists()]
        if not files:
            return
        self.progress.show()
        self.progress.setValue(0)

        def done(ok: bool, err: str) -> None:
            self.progress.hide()
            self.toast.show_message(tr("Done") if ok else tr("Error: {e}", e=err))
            if cut and ok:
                self.clipboard = ([], False)

        self.threads.append(start_transfer(self, files, Path(self.current()), cut,
                                           lambda v, _n: self.progress.setValue(v), done))

    def trash(self) -> None:
        sel = self.selected()
        if not sel:
            return
        in_trash = str(sel[0]).startswith(str(TRASH))
        if in_trash or not confirm(self, tr("Move to trash"),
                                   tr("Move {n} items to trash?", n=len(sel)), yes=tr("Move to trash")):
            if in_trash:
                self.delete_permanently()
            return
        from PySide6.QtCore import QFile
        failed = [p for p in sel if not QFile.moveToTrash(str(p))]
        if failed:
            self.toast.show_message(tr("Could not move {n} items to trash", n=len(failed)))

    def delete_permanently(self) -> None:
        sel = self.selected()
        if not sel or not confirm(self, tr("Delete permanently"),
                                  tr("Permanently delete {n} items? This cannot be undone.", n=len(sel)),
                                  danger=True, yes=tr("Delete")):
            return
        for p in sel:
            try:
                shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
            except OSError as exc:
                self.toast.show_message(str(exc))

    def empty_trash(self) -> None:
        if confirm(self, tr("Empty trash"), tr("Permanently delete all items in trash?"), danger=True,
                   yes=tr("Empty trash")):
            base = TRASH.parent
            for sub in ("files", "info"):
                d = base / sub
                if d.is_dir():
                    for p in d.iterdir():
                        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)

    def open_terminal(self) -> None:
        for term in ("nova-terminal", "konsole", "x-terminal-emulator"):
            if shutil.which(term):
                subprocess.Popen([term, "--workdir", self.current()] if term != "x-terminal-emulator" else [term],
                                 cwd=self.current())
                return

    def properties(self) -> None:
        sel = self.selected() or [Path(self.current())]
        p = sel[0]
        info = QFileInfo(str(p))
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Properties"))
        form = QFormLayout(dlg)
        size = dir_size(p) if p.is_dir() else info.size()
        rows = [(tr("Name"), p.name or "/"), (tr("Location"), str(p.parent)),
                (tr("Type"), tr("Folder") if p.is_dir() else (self.model.type(self.model.index(str(p))))),
                (tr("Size"), human(size)),
                (tr("Modified"), time.strftime("%Y-%m-%d %H:%M", time.localtime(info.lastModified().toSecsSinceEpoch()))),
                (tr("Owner"), info.owner()), (tr("Permissions"), oct(p.stat().st_mode & 0o777) if p.exists() else "")]
        for k, v in rows:
            lbl = QLabel(v)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(k + ":", lbl)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        dlg.exec()

    def _menu(self, pos) -> None:
        m = QMenu(self)
        sel = self.selected()
        in_trash = self.current().startswith(str(TRASH))
        if sel:
            m.addAction(icon("document-open"), tr("Open"), lambda: [QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))) for p in sel])
            m.addSeparator()
            m.addAction(icon("edit-cut"), tr("Cut"), lambda: self.copy(cut=True))
            m.addAction(icon("edit-copy"), tr("Copy"), self.copy)
        m.addAction(icon("edit-paste"), tr("Paste"), self.paste)
        if sel:
            m.addAction(icon("edit-rename"), tr("Rename"), self.rename)
            m.addSeparator()
            if not in_trash:
                m.addAction(icon("user-trash"), tr("Move to trash"), self.trash)
            m.addAction(icon("edit-delete"), tr("Delete permanently"), self.delete_permanently)
        if in_trash:
            m.addAction(icon("trash-empty"), tr("Empty trash"), self.empty_trash)
        m.addSeparator()
        m.addAction(icon("folder-new"), tr("New folder"), self.new_folder)
        m.addAction(icon("utilities-terminal"), tr("Open terminal here"), self.open_terminal)
        m.addAction(icon("document-properties"), tr("Properties"), self.properties)
        m.exec(self._view().viewport().mapToGlobal(pos))

    def _shortcuts(self) -> None:
        for seq, fn in [(QKeySequence.Copy, self.copy), (QKeySequence.Cut, lambda: self.copy(True)),
                        (QKeySequence.Paste, self.paste), (QKeySequence.Delete, self.trash),
                        ("Shift+Delete", self.delete_permanently), ("F2", self.rename),
                        ("Ctrl+H", self.hidden_btn.toggle), ("Ctrl+Shift+N", self.new_folder),
                        ("Alt+Left", self.go_back), ("Alt+Right", self.go_forward), ("Alt+Up", self.go_up),
                        ("Backspace", self.go_up), ("Ctrl+L", self.path_edit.setFocus),
                        ("Ctrl+F", self.search.setFocus), ("F5", lambda: self.navigate(self.current(), False)),
                        ("Alt+Return", self.properties)]:
            QShortcut(QKeySequence(seq), self, activated=fn)


def main() -> int:
    start = None
    for a in sys.argv[1:]:
        if not a.startswith("-"):
            start = QUrl(a).toLocalFile() if a.startswith("file:") else a
    return novaapp.run(lambda: Files(start), "nova-files", "Nova Files")


if __name__ == "__main__":
    sys.exit(main())
