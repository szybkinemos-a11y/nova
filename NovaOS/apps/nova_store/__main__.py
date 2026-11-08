"""Nova Store – sklep z aplikacjami: polecane, kategorie, wyszukiwanie (APT + Flathub),
instalacja, odinstalowanie i aktualizacje z paskiem postępu."""
from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy, QSplitter, QToolButton, QVBoxLayout, QWidget)

from novakit import app as novaapp
from novakit.i18n import tr
from novakit.proc import Task, run
from novakit.widgets import SearchField, Sidebar, Toast, confirm, icon, notify, title
from nova_store.backends import BACKENDS, Apt, App, Flatpak, load_catalog, refresh_state


def letter_icon(text: str, size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    from PySide6.QtGui import QLinearGradient
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#A855F7"))
    g.setColorAt(1, QColor("#3B82F6"))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, size * 0.26, size * 0.26)
    f = QFont()
    f.setPixelSize(int(size * 0.45))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(pm.rect(), Qt.AlignCenter, (text or "?")[0].upper())
    p.end()
    return QIcon(pm)


def app_icon(a: App) -> QIcon:
    path = a.icon_path()
    if path:
        return QIcon(path)
    for name in (a.id, a.id.split(".")[-1].lower(), a.name.lower()):
        ic = QIcon.fromTheme(name)
        if not ic.isNull():
            return ic
    return letter_icon(a.name)


class Worker(QRunnable):
    class S(QObject):
        done = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn, self.s = fn, Worker.S()

    def run(self):
        try:
            self.s.done.emit(self.fn())
        except Exception as exc:  # noqa: BLE001
            self.s.done.emit(exc)


class AppCard(QWidget):
    action = Signal(str, object)   # ("install"|"remove"|"open"|"update", App)

    def __init__(self, a: App):
        super().__init__()
        self.app = a
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        ic = QLabel()
        ic.setPixmap(app_icon(a).pixmap(QSize(56, 56)))
        ic.setFixedSize(58, 58)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(f"<b>{a.name}</b>")
        src = "Flathub" if a.source == "flatpak" else "Ubuntu (APT)"
        meta = QLabel(f"{src}{' · ' + a.version if a.version else ''}")
        meta.setObjectName("Subtitle")
        summ = QLabel(a.summary)
        summ.setWordWrap(True)
        summ.setMaximumHeight(36)
        text.addWidget(name)
        text.addWidget(summ)
        text.addWidget(meta)
        btns = QVBoxLayout()
        if a.installed:
            if a.update:
                b = QPushButton(tr("Update"))
                b.setObjectName("Accent")
                b.clicked.connect(lambda: self.action.emit("update", a))
                btns.addWidget(b)
            o = QPushButton(tr("Open"))
            o.clicked.connect(lambda: self.action.emit("open", a))
            r = QToolButton()
            r.setIcon(icon("edit-delete"))
            r.setToolTip(tr("Uninstall"))
            r.setAutoRaise(True)
            r.clicked.connect(lambda: self.action.emit("remove", a))
            row = QHBoxLayout()
            row.addWidget(o)
            row.addWidget(r)
            btns.addLayout(row)
        else:
            b = QPushButton(tr("Install"))
            b.setObjectName("Accent")
            b.clicked.connect(lambda: self.action.emit("install", a))
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addWidget(ic, 0, Qt.AlignTop)
        lay.addLayout(text, 1)
        lay.addLayout(btns)


class Store(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova Store")
        self.resize(1180, 760)
        self.categories, self.catalog = load_catalog()
        self.pool = QThreadPool.globalInstance()
        self.queue: list[tuple[str, App]] = []
        self.task: Task | None = None
        self.page = "featured"
        self.updates: list[App] = []

        split = QSplitter()
        self.side = Sidebar(220)
        self.side.add(tr("Discover"), "nova-store", data="featured")
        for c in self.categories:
            self.side.add(tr(c["name"]), c["icon"], "applications-other", data="cat:" + c["id"])
        self.side.add(tr("Installed"), "emblem-checked", "dialog-ok", data="installed")
        self.upd_item = self.side.add(tr("Updates"), "system-software-update", "update-none", data="updates")
        self.side.currentItemChanged.connect(lambda it, _p: it and self.show_page(it.data(Qt.UserRole)))
        split.addWidget(self.side)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(20, 14, 20, 10)
        top = QHBoxLayout()
        self.header = title(tr("Discover"), tr("Apps from Ubuntu repositories and Flathub"))
        self.search = SearchField(tr("Search apps (APT + Flathub)…"))
        self.search.setMinimumWidth(320)
        self.search.returnPressed.connect(self.do_search)
        top.addWidget(self.header, 1)
        top.addWidget(self.search)
        rv.addLayout(top)
        self.banner = QWidget()
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(0, 0, 0, 0)
        self.banner_lbl = QLabel(tr("Flathub is not configured – Flatpak apps are unavailable."))
        add = QPushButton(tr("Enable Flathub"))
        add.setObjectName("Accent")
        add.clicked.connect(self.enable_flathub)
        bl.addWidget(self.banner_lbl, 1)
        bl.addWidget(add)
        self.banner.hide()
        rv.addWidget(self.banner)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        rv.addWidget(self.scroll, 1)

        # pasek zadań: postęp + log
        self.task_bar = QWidget()
        tl = QVBoxLayout(self.task_bar)
        tl.setContentsMargins(0, 6, 0, 0)
        row = QHBoxLayout()
        self.task_lbl = QLabel()
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 100)
        self.log_btn = QToolButton()
        self.log_btn.setText(tr("Details"))
        self.log_btn.setCheckable(True)
        row.addWidget(self.task_lbl, 1)
        row.addWidget(self.task_progress, 2)
        row.addWidget(self.log_btn)
        tl.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)
        self.log.hide()
        self.log_btn.toggled.connect(self.log.setVisible)
        tl.addWidget(self.log)
        self.task_bar.hide()
        rv.addWidget(self.task_bar)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.toast = Toast(self)

        self._async(lambda: Flatpak.available() and Flatpak.has_flathub(),
                    lambda ok: self.banner.setVisible(Flatpak.available() and not ok))
        self.side.setCurrentRow(0)
        self.check_updates()

    # ------------------------------------------------------------ strony
    def _async(self, fn, cb) -> None:
        w = Worker(fn)
        w.s.done.connect(cb)
        self.pool.start(w)

    def _set_header(self, t: str, sub: str) -> None:
        self.header.findChild(QLabel, "Title").setText(t)
        self.header.findChild(QLabel, "Subtitle").setText(sub)

    def show_page(self, page: str) -> None:
        self.page = page
        if page == "featured":
            self._set_header(tr("Discover"), tr("Hand-picked apps for NovaOS"))
            apps = [a for a in self.catalog if a.featured]
        elif page.startswith("cat:"):
            cat = next(c for c in self.categories if c["id"] == page[4:])
            self._set_header(tr(cat["name"]), tr("Recommended apps"))
            apps = [a for a in self.catalog if a.category == cat["id"]]
        elif page == "installed":
            self._set_header(tr("Installed"), tr("Apps installed from this store and Flathub"))
            self._loading()
            self._async(self._installed_apps, self._render)
            return
        elif page == "updates":
            self._set_header(tr("Updates"), tr("Keep your system secure and up to date"))
            self._render_updates()
            return
        else:
            return
        self._loading()
        self._async(lambda: (refresh_state(apps), apps)[1], self._render)

    def _installed_apps(self) -> list[App]:
        refresh_state(self.catalog)
        apps = [a for a in self.catalog if a.installed]
        known = {a.id for a in apps}
        if Flatpak.available():
            for aid, (name, ver) in Flatpak.installed().items():
                if aid not in known:
                    apps.append(App(aid, "flatpak", name or aid, "", version=ver, installed=True))
        return apps

    def _loading(self) -> None:
        lbl = QLabel(tr("Loading…"))
        lbl.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(lbl)

    def _render(self, apps) -> None:
        if isinstance(apps, Exception):
            self.scroll.setWidget(QLabel(str(apps)))
            return
        upd = {a.key: a.update for a in self.updates}
        for a in apps:
            a.update = upd.get(a.key, "")
        w = QWidget()
        g = QGridLayout(w)
        g.setSpacing(12)
        g.setContentsMargins(0, 4, 8, 4)
        if not apps:
            empty = QLabel(tr("Nothing here yet."))
            empty.setObjectName("Subtitle")
            g.addWidget(empty, 0, 0)
        for i, a in enumerate(apps):
            card = AppCard(a)
            card.action.connect(self.on_action)
            g.addWidget(card, i // 2, i % 2)
        g.setRowStretch(len(apps) // 2 + 1, 1)
        self.scroll.setWidget(w)

    def do_search(self) -> None:
        q = self.search.text().strip()
        if len(q) < 2:
            return
        self.side.clearSelection()
        self.page = "search"
        self._set_header(tr("Search: {q}", q=q), tr("Results from Flathub and Ubuntu repositories"))
        self._loading()

        def work():
            res = []
            if Flatpak.available():
                res += Flatpak.search(q, 30)
            if Apt.available():
                res += Apt.search(q, 30)
            return res
        self._async(work, self._render)

    # ------------------------------------------------------------ aktualizacje
    def check_updates(self) -> None:
        def work():
            apps = []
            if Apt.available():
                for name, ver in Apt.upgradable().items():
                    apps.append(App(name, "apt", name, tr("System package"), installed=True, update=ver, version=ver))
            if Flatpak.available():
                for aid, ver in Flatpak.upgradable().items():
                    apps.append(App(aid, "flatpak", aid.split(".")[-1], "", installed=True, update=ver or "new", version=ver))
            return apps

        def done(apps):
            self.updates = apps if isinstance(apps, list) else []
            n = len(self.updates)
            self.upd_item.setText(tr("Updates") + (f"  ({n})" if n else ""))
            if self.page == "updates":
                self._render_updates()
        self._async(work, done)

    def _render_updates(self) -> None:
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        info = QLabel(tr("{n} updates available", n=len(self.updates)) if self.updates else tr("Your system is up to date."))
        info.setObjectName("Section")
        refresh = QPushButton(tr("Check for updates"))
        refresh.clicked.connect(self.refresh_repos)
        upd_all = QPushButton(tr("Update all"))
        upd_all.setObjectName("Accent")
        upd_all.setEnabled(bool(self.updates))
        upd_all.clicked.connect(self.update_all)
        row.addWidget(info, 1)
        row.addWidget(refresh)
        row.addWidget(upd_all)
        v.addLayout(row)
        for a in self.updates[:200]:
            lbl = QLabel(f"• <b>{a.name}</b>  →  {a.update}  <span style='opacity:.6'>({'Flathub' if a.source == 'flatpak' else 'APT'})</span>")
            v.addWidget(lbl)
        v.addStretch(1)
        self.scroll.setWidget(w)

    def refresh_repos(self) -> None:
        cmds = [["pkexec", "/usr/libexec/novaos/nova-helper", "apt-update"]]
        if Flatpak.available():
            cmds.append(["flatpak", "update", "--appstream", "-y"])
        self._run_task(tr("Refreshing package lists"), cmds, after=self.check_updates)

    def update_all(self) -> None:
        cmds = Apt.update_cmd() if any(a.source == "apt" for a in self.updates) else []
        if any(a.source == "flatpak" for a in self.updates):
            cmds += Flatpak.update_cmd()
        self._run_task(tr("Installing updates"), cmds, after=self.check_updates)

    def enable_flathub(self) -> None:
        self._run_task(tr("Enabling Flathub"), Flatpak.add_flathub_cmd(),
                       after=lambda: self.banner.setVisible(not Flatpak.has_flathub()))

    # ------------------------------------------------------------ akcje
    def on_action(self, kind: str, a: App) -> None:
        backend = BACKENDS[a.source]
        if kind == "open":
            self.launch(a)
        elif kind == "install":
            self._run_task(tr("Installing {n}", n=a.name), backend.install_cmd([a.id]), notify_app=a)
        elif kind == "update":
            cmds = backend.install_cmd([a.id]) if a.source == "apt" else [["flatpak", "update", "-y", "--noninteractive", a.id]]
            self._run_task(tr("Updating {n}", n=a.name), cmds, after=self.check_updates)
        elif kind == "remove":
            if confirm(self, tr("Uninstall"), tr("Uninstall {n}? Your personal files are not deleted.", n=a.name),
                       danger=True, yes=tr("Uninstall")):
                self._run_task(tr("Removing {n}", n=a.name), backend.remove_cmd([a.id]))

    def launch(self, a: App) -> None:
        if a.source == "flatpak":
            subprocess.Popen(["flatpak", "run", a.id])
            return
        files = [l for l in run(["dpkg", "-L", a.id]).out.splitlines()
                 if l.startswith("/usr/share/applications/") and l.endswith(".desktop")]
        for f in files:
            try:
                for line in Path(f).read_text(encoding="utf-8").splitlines():
                    if line.startswith("Exec="):
                        args = [x for x in shlex.split(line[5:]) if not x.startswith("%")]
                        subprocess.Popen(args)
                        return
            except OSError:
                continue
        self.toast.show_message(tr("{n} has no graphical launcher (it is a command-line tool).", n=a.name))

    def _run_task(self, label: str, cmds: list[list[str]], after=None, notify_app: App | None = None) -> None:
        if self.task is not None:
            self.toast.show_message(tr("Please wait for the current operation to finish"))
            return
        self.task_bar.show()
        self.task_lbl.setText(label + "…")
        self.task_progress.setRange(0, 0)
        self.log.appendPlainText(f"\n=== {label} ===")
        self.task = Task(cmds, self)
        self.task.line.connect(self._task_line)
        self.task.progress.connect(lambda p: (self.task_progress.setRange(0, 100), self.task_progress.setValue(p)))

        def finished(ok: bool) -> None:
            self.task = None
            self.task_progress.setRange(0, 100)
            self.task_progress.setValue(100 if ok else 0)
            self.task_lbl.setText((tr("Done: {l}", l=label)) if ok else tr("Failed: {l}", l=label))
            if not ok:
                self.log_btn.setChecked(True)
            if ok and notify_app:
                notify(tr("{n} installed", n=notify_app.name), tr("You can find it in the Start menu."), "nova-store", "Nova Store")
            if after:
                after()
            if self.page not in ("search", "updates"):
                self.show_page(self.page)
        self.task.finished.connect(finished)
        self.task.start()

    def _task_line(self, text: str) -> None:
        if text.startswith(("pmstatus:", "dlstatus:")):   # postęp APT (APT::Status-Fd)
            parts = text.split(":", 3)
            try:
                pct = float(parts[2])
                self.task_progress.setRange(0, 100)
                self.task_progress.setValue(int(pct if parts[0] == "pmstatus" else pct * 0.4))
                self.task_lbl.setText(parts[3][:80])
            except (IndexError, ValueError):
                pass
            return
        self.log.appendPlainText(text)


def main() -> int:
    return novaapp.run(Store, "nova-store", "Nova Store")


if __name__ == "__main__":
    sys.exit(main())
