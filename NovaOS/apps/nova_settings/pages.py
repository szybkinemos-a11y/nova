"""Strony Nova Settings."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QDateTime, QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QScrollArea,
                               QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from novakit.i18n import tr
from novakit.proc import Task, privileged
from novakit.widgets import card, confirm, icon, section, title
from nova_settings import backend as B


# ---------------------------------------------------------------- narzędzia
class _Job(QRunnable):
    class S(QObject):
        done = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn, self.s = fn, _Job.S()

    def run(self):
        try:
            res = self.fn()
        except Exception as exc:  # noqa: BLE001
            res = exc
        self.s.done.emit(res)


_JOBS: list[_Job] = []


def bg(fn, cb=None) -> None:
    """Uruchamia fn w tle, wynik przekazuje do cb w wątku GUI."""
    job = _Job(fn)
    _JOBS.append(job)
    job.setAutoDelete(False)

    def finish(res):
        _JOBS.remove(job)
        if cb:
            cb(res)
    job.s.done.connect(finish)
    QThreadPool.globalInstance().start(job)


def row(label: str, widget: QWidget, hint: str | None = None) -> QHBoxLayout:
    h = QHBoxLayout()
    v = QVBoxLayout()
    v.setSpacing(0)
    v.addWidget(QLabel(label))
    if hint:
        s = QLabel(hint)
        s.setObjectName("Subtitle")
        s.setWordWrap(True)
        v.addWidget(s)
    h.addLayout(v, 1)
    h.addWidget(widget)
    return h


class Switch(QCheckBox):
    """Przełącznik w stylu NovaOS."""

    def __init__(self, checked: bool = False):
        super().__init__()
        self.setChecked(checked)
        self.setStyleSheet("""
            QCheckBox::indicator { width: 40px; height: 22px; border-radius: 11px; background: rgba(127,127,127,.35); }
            QCheckBox::indicator:checked { background: palette(highlight); }
        """)


class Page(QScrollArea):
    TITLE = ""
    SUBTITLE = ""
    ICON = ""

    def __init__(self, window):
        super().__init__()
        self.win = window
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(28, 22, 28, 22)
        self.lay.setSpacing(12)
        self.lay.addWidget(title(tr(self.TITLE), tr(self.SUBTITLE)))
        self.setWidget(body)
        self.build()
        self.lay.addStretch(1)

    def build(self) -> None:
        raise NotImplementedError

    def refresh(self) -> None:
        """Wywoływane przy każdym wejściu na stronę."""

    def toast(self, text: str) -> None:
        self.win.toast.show_message(text)

    def add_card(self, *rows) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(10)
        for r in rows:
            if isinstance(r, QWidget):
                v.addWidget(r)
            else:
                v.addLayout(r)
        self.lay.addWidget(card(v))
        return v


# ================================================================ Wygląd
class AppearancePage(Page):
    TITLE, SUBTITLE, ICON = "Appearance", "Theme, accent colour, wallpaper and effects", "preferences-desktop-theme"

    def build(self):
        self.lay.addWidget(section(tr("Theme")))
        themes = QHBoxLayout()
        self.theme_btns = {}
        for mode, label in (("dark", tr("Dark")), ("light", tr("Light"))):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setMinimumSize(170, 90)
            b.setStyleSheet(f"""QPushButton {{ border-radius: 14px; font-weight:600;
                background: {'#15131F' if mode == 'dark' else '#F4F3FA'}; color: {'white' if mode == 'dark' else '#1C1A2B'};
                border: 2px solid rgba(127,127,127,.3); }}
                QPushButton:checked {{ border: 3px solid palette(highlight); }}""")
            b.clicked.connect(lambda _=False, m=mode: self.set_theme(m))
            themes.addWidget(b)
            self.theme_btns[mode] = b
        themes.addStretch(1)
        self.add_card(themes)

        self.lay.addWidget(section(tr("Accent colour")))
        acc = QHBoxLayout()
        for name, color in B.ACCENTS.items():
            b = QToolButton()
            b.setFixedSize(34, 34)
            b.setToolTip(tr(name))
            b.setStyleSheet(f"QToolButton {{ background:{color}; border-radius:17px; border:2px solid rgba(255,255,255,.25);}}"
                            f"QToolButton:hover {{ border:3px solid white; }}")
            b.clicked.connect(lambda _=False, c=color: self.set_accent(c))
            acc.addWidget(b)
        custom = QPushButton(tr("Custom…"))
        custom.clicked.connect(self.pick_accent)
        acc.addWidget(custom)
        acc.addStretch(1)
        self.add_card(acc)

        self.lay.addWidget(section(tr("Wallpaper")))
        self.walls = QListWidget()
        self.walls.setViewMode(QListWidget.IconMode)
        self.walls.setIconSize(QSize(200, 112))
        self.walls.setGridSize(QSize(216, 150))
        self.walls.setResizeMode(QListWidget.Adjust)
        self.walls.setMovement(QListWidget.Static)
        self.walls.setMinimumHeight(330)
        self.walls.itemActivated.connect(lambda it: self.set_wall(Path(it.data(Qt.UserRole))))
        self.walls.itemClicked.connect(lambda it: self.set_wall(Path(it.data(Qt.UserRole))))
        own = QPushButton(tr("Choose image…"))
        own.clicked.connect(self.choose_wall)
        self.add_card(self.walls, own)

        self.lay.addWidget(section(tr("Effects")))
        self.blur = Switch(B.effect_enabled("blur"))
        self.blur.toggled.connect(lambda on: B.set_effect("blur", on))
        self.corners = Switch(B.effect_enabled("kwin4_effect_shapecorners"))
        self.corners.toggled.connect(lambda on: B.set_effect("kwin4_effect_shapecorners", on))
        self.wobbly = Switch(B.effect_enabled("wobblywindows", False))
        self.wobbly.toggled.connect(lambda on: B.set_effect("wobblywindows", on))
        self.anim = QSlider(Qt.Horizontal)
        self.anim.setRange(0, 6)
        self.anim.setFixedWidth(220)
        factor = float(B.kread("kdeglobals", "KDE", "AnimationDurationFactor", "0.707") or 0.707)
        self.anim.setValue(max(0, min(6, round(6 - factor * 3))))
        self.anim.valueChanged.connect(lambda v: B.set_animation_speed(0 if v == 6 else (6 - v) / 3))
        self.add_card(row(tr("Blur and transparency"), self.blur, tr("Frosted-glass panels, menus and windows")),
                      row(tr("Rounded window corners"), self.corners),
                      row(tr("Wobbly windows"), self.wobbly),
                      row(tr("Animation speed"), self.anim, tr("Slow ← → Instant")))

    def refresh(self):
        mode = B.current_theme()
        for m, b in self.theme_btns.items():
            b.setChecked(m == mode)
        if not self.walls.count():
            for p in B.wallpapers():
                prev = B.wallpaper_preview(p)
                pm = QPixmap(str(prev))
                it = QListWidgetItem(QIcon(pm.scaled(400, 224, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)),
                                     p.stem if p.is_file() else p.name)
                it.setData(Qt.UserRole, str(p))
                self.walls.addItem(it)

    def set_theme(self, mode: str):
        bg(lambda: B.set_theme(mode, B.current_accent()), lambda ok: (self.refresh(), self.toast(tr("Theme changed"))))
        for m, b in self.theme_btns.items():
            b.setChecked(m == mode)

    def set_accent(self, color: str):
        bg(lambda: B.set_accent(color), lambda ok: self.toast(tr("Accent colour changed")))

    def pick_accent(self):
        c = QColorDialog.getColor(QColor(B.current_accent()), self, tr("Accent colour"))
        if c.isValid():
            self.set_accent(c.name())

    def set_wall(self, path: Path):
        bg(lambda: B.set_wallpaper(path), lambda ok: self.toast(tr("Wallpaper changed") if ok else tr("Could not change wallpaper")))

    def choose_wall(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Choose image…"), str(Path.home()), "Images (*.png *.jpg *.jpeg *.webp)")
        if f:
            self.set_wall(Path(f))


# ================================================================ Ekran
class DisplayPage(Page):
    TITLE, SUBTITLE, ICON = "Display", "Resolution, refresh rate, scaling and night light", "video-display"

    def build(self):
        self.box = QVBoxLayout()
        self.lay.addLayout(self.box)
        self.night = Switch(B.kread("kwinrc", "NightColor", "Active", "false") == "true")
        self.night.toggled.connect(lambda on: (B.kwrite("kwinrc", "NightColor", "Active", str(on).lower()), B.kwin_reconfigure()))
        self.lay.addWidget(section(tr("Night light")))
        self.add_card(row(tr("Night light"), self.night, tr("Warmer colours in the evening reduce eye strain")))

    def refresh(self):
        while self.box.count():
            it = self.box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        outs = B.outputs()
        if not outs:
            lbl = QLabel(tr("Display information is available in a KDE Plasma session (kscreen-doctor)."))
            lbl.setObjectName("Subtitle")
            self.box.addWidget(lbl)
            return
        for o in outs:
            v = QVBoxLayout()
            v.addWidget(section(f"{tr('Screen')} {o.name}"))
            res = QComboBox()
            for m in o.modes:
                res.addItem(m.label, m.id)
                if m.id == o.current:
                    res.setCurrentIndex(res.count() - 1)
            scale = QComboBox()
            for s in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0):
                scale.addItem(f"{int(s * 100)}%", s)
                if abs(s - o.scale) < 0.01:
                    scale.setCurrentIndex(scale.count() - 1)
            apply_btn = QPushButton(tr("Apply"))
            apply_btn.setObjectName("Accent")
            apply_btn.clicked.connect(lambda _=False, o=o, r=res, s=scale: self.apply(o, r.currentData(), s.currentData()))
            v.addLayout(row(tr("Resolution and refresh rate"), res))
            v.addLayout(row(tr("Scale"), scale))
            v.addWidget(apply_btn, 0, Qt.AlignRight)
            self.box.addWidget(card(v))

    def apply(self, o, mode_id, scale):
        old_mode, old_scale = o.current, o.scale
        r = B.apply_output(o.name, mode_id, scale)
        if not r.ok:
            self.toast(tr("Could not apply: {e}", e=r.err.strip()[:120]))
            return
        box = QMessageBox(QMessageBox.Question, tr("Keep display settings?"),
                          tr("Keep these display settings? They will be reverted in 15 seconds."),
                          QMessageBox.Yes | QMessageBox.No, self)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(15000, lambda: box.done(QMessageBox.No))
        if box.exec() != QMessageBox.Yes:
            B.apply_output(o.name, old_mode, old_scale)
        self.refresh()


# ================================================================ Dźwięk
class SoundPage(Page):
    TITLE, SUBTITLE, ICON = "Sound", "Output and input devices, volume", "audio-volume-high"

    def build(self):
        self.widgets = {}
        for kind, label in (("sinks", tr("Output")), ("sources", tr("Input (microphone)"))):
            self.lay.addWidget(section(label))
            dev = QComboBox()
            dev.activated.connect(lambda _i, k=kind, d=dev: (B.set_default(k, d.currentData()), self.refresh()))
            vol = QSlider(Qt.Horizontal)
            vol.setRange(0, 150)
            vol.setFixedWidth(260)
            pct = QLabel("0%")
            pct.setFixedWidth(44)
            vol.valueChanged.connect(lambda v, p=pct: p.setText(f"{v}%"))
            vol.sliderReleased.connect(lambda k=kind, d=dev, s=vol: B.set_volume(k, d.currentData(), s.value()))
            mute = Switch()
            mute.toggled.connect(lambda on, k=kind, d=dev: B.set_mute(k, d.currentData(), on))
            vh = QHBoxLayout()
            vh.addWidget(vol)
            vh.addWidget(pct)
            w = QWidget()
            w.setLayout(vh)
            self.add_card(row(tr("Device"), dev), row(tr("Volume"), w), row(tr("Mute"), mute))
            self.widgets[kind] = (dev, vol, mute)

    def refresh(self):
        for kind, (dev, vol, mute) in self.widgets.items():
            devs, default = B.audio_devices(kind)
            dev.blockSignals(True)
            dev.clear()
            for d in devs:
                dev.addItem(d.description, d.name)
                if d.name == default:
                    dev.setCurrentIndex(dev.count() - 1)
                    vol.blockSignals(True)
                    vol.setValue(d.volume)
                    vol.blockSignals(False)
                    vol.valueChanged.emit(d.volume)
                    mute.blockSignals(True)
                    mute.setChecked(d.muted)
                    mute.blockSignals(False)
            if not devs:
                dev.addItem(tr("No devices"))
            dev.blockSignals(False)


# ================================================================ Wi-Fi
class WifiPage(Page):
    TITLE, SUBTITLE, ICON = "Wi-Fi", "Wireless networks", "network-wireless"

    def build(self):
        self.enabled = Switch()
        self.enabled.toggled.connect(lambda on: (B.wifi_set(on), self.scan() if on else self.list.clear()))
        rescan = QPushButton(tr("Scan"))
        rescan.clicked.connect(self.scan)
        h = row(tr("Wi-Fi"), self.enabled)
        h.addWidget(rescan)
        self.add_card(h)
        self.status = QLabel()
        self.status.setObjectName("Subtitle")
        self.lay.addWidget(self.status)
        self.list = QListWidget()
        self.list.setMinimumHeight(360)
        self.list.itemActivated.connect(self.activate)
        acts = QHBoxLayout()
        for label, fn in ((tr("Connect"), lambda: self.activate(self.list.currentItem())),
                          (tr("Disconnect"), self.disconnect), (tr("Forget"), self.forget)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            acts.addWidget(b)
        acts.addStretch(1)
        self.add_card(self.list, acts)

    def refresh(self):
        on = B.wifi_enabled()
        self.enabled.blockSignals(True)
        self.enabled.setChecked(on)
        self.enabled.blockSignals(False)
        if on:
            self.scan()

    def scan(self):
        self.status.setText(tr("Scanning…"))
        bg(B.wifi_scan, self.show)

    def show(self, nets):
        self.list.clear()
        if isinstance(nets, Exception) or not nets:
            self.status.setText(tr("No networks found (is there a wireless card?)"))
            return
        self.status.setText(tr("{n} networks", n=len(nets)))
        for n in nets:
            bars = "▂▄▆█"[: max(1, min(4, n.signal // 25 + 1))]
            lock = "🔒 " if n.security and n.security != "--" else ""
            it = QListWidgetItem(icon("network-wireless"), f"{n.ssid}   {lock}{bars}  {n.signal}%" + ("   ✔ " + tr("Connected") if n.active else ""))
            it.setData(Qt.UserRole, n)
            self.list.addItem(it)

    def activate(self, it):
        if not it:
            return
        n = it.data(Qt.UserRole)
        pw = None
        if n.security and n.security != "--":
            pw, ok = QInputDialog.getText(self, tr("Connect to {s}", s=n.ssid), tr("Password:"), QLineEdit.Password)
            if not ok:
                return
        self.status.setText(tr("Connecting to {s}…", s=n.ssid))
        bg(lambda: B.wifi_connect(n.ssid, pw or None),
           lambda r: (self.toast(tr("Connected") if r.ok else tr("Connection failed: {e}", e=(r.err or r.out).strip()[:100])), self.scan()))

    def disconnect(self):
        it = self.list.currentItem()
        if it:
            bg(lambda: B.wifi_disconnect(it.data(Qt.UserRole).ssid), lambda r: self.scan())

    def forget(self):
        it = self.list.currentItem()
        if it and confirm(self, tr("Forget"), tr("Forget network {s}? The saved password will be deleted.", s=it.data(Qt.UserRole).ssid)):
            bg(lambda: B.wifi_forget(it.data(Qt.UserRole).ssid), lambda r: self.scan())


# ================================================================ Bluetooth
class BluetoothPage(Page):
    TITLE, SUBTITLE, ICON = "Bluetooth", "Pair and connect devices", "preferences-system-bluetooth"

    def build(self):
        self.power = Switch()
        self.power.toggled.connect(lambda on: bg(lambda: B.bt_set_power(on), lambda r: self.refresh()))
        scan = QPushButton(tr("Search for devices"))
        scan.clicked.connect(self.scan)
        h = row(tr("Bluetooth"), self.power)
        h.addWidget(scan)
        self.add_card(h)
        self.status = QLabel()
        self.status.setObjectName("Subtitle")
        self.lay.addWidget(self.status)
        self.list = QListWidget()
        self.list.setMinimumHeight(300)
        acts = QHBoxLayout()
        for label, act in ((tr("Pair"), "pair"), (tr("Connect"), "connect"), (tr("Disconnect"), "disconnect"),
                           (tr("Remove"), "remove")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, a=act: self.act(a))
            acts.addWidget(b)
        acts.addStretch(1)
        self.add_card(self.list, acts)

    def refresh(self):
        def work():
            if not B.bt_available():
                return None
            return B.bt_powered(), B.bt_devices()

        def done(res):
            if not res or isinstance(res, Exception):
                self.status.setText(tr("No Bluetooth adapter found."))
                self.power.setEnabled(False)
                return
            powered, devs = res
            self.power.blockSignals(True)
            self.power.setChecked(powered)
            self.power.blockSignals(False)
            self.list.clear()
            for d in devs:
                state = tr("Connected") if d.connected else (tr("Paired") if d.paired else "")
                it = QListWidgetItem(icon("bluetooth", "preferences-system-bluetooth"), f"{d.name}   {state}")
                it.setData(Qt.UserRole, d.mac)
                self.list.addItem(it)
            self.status.setText(tr("{n} devices", n=len(devs)) if powered else tr("Bluetooth is off"))
        bg(work, done)

    def scan(self):
        self.status.setText(tr("Searching for devices (8 s)…"))
        bg(B.bt_scan, lambda _r: self.refresh())

    def act(self, action):
        it = self.list.currentItem()
        if not it:
            return
        if action == "remove" and not confirm(self, tr("Remove"), tr("Remove this device?")):
            return
        self.status.setText("…")
        bg(lambda: B.bt_action(action, it.data(Qt.UserRole)),
           lambda r: (self.toast(tr("Done") if r.ok else tr("Failed")), self.refresh()))


# ================================================================ Użytkownicy
class UserDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Add user"))
        f = QFormLayout(self)
        self.full = QLineEdit()
        self.login = QLineEdit()
        self.full.textChanged.connect(lambda t: self.login.setText(
            "".join(c for c in t.lower().split(" ")[0] if c.isalnum())[:32]))
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        self.strength = QProgressBar()
        self.strength.setRange(0, 4)
        self.pw.textChanged.connect(lambda t: self.strength.setValue(B.password_strength(t)[0]))
        self.admin = QCheckBox(tr("Administrator (can install software and change system settings)"))
        f.addRow(tr("Full name:"), self.full)
        f.addRow(tr("Login:"), self.login)
        f.addRow(tr("Password:"), self.pw)
        f.addRow(tr("Repeat password:"), self.pw2)
        f.addRow(tr("Strength:"), self.strength)
        f.addRow(self.admin)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.check)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def check(self):
        if not B.valid_login(self.login.text()):
            QMessageBox.warning(self, tr("Add user"), tr("Login may contain only lowercase letters, digits, '-' and '_'."))
        elif len(self.pw.text()) < 4 or self.pw.text() != self.pw2.text():
            QMessageBox.warning(self, tr("Add user"), tr("Passwords do not match or are too short."))
        else:
            self.accept()


class UsersPage(Page):
    TITLE, SUBTITLE, ICON = "Users", "Accounts on this computer", "system-users"

    def build(self):
        self.list = QListWidget()
        self.list.setIconSize(QSize(40, 40))
        self.list.setMinimumHeight(260)
        acts = QHBoxLayout()
        for label, fn in ((tr("Add user…"), self.add), (tr("Toggle administrator"), self.toggle_admin),
                          (tr("Set password…"), self.set_pw), (tr("Delete user…"), self.delete)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            acts.addWidget(b)
        acts.addStretch(1)
        self.add_card(self.list, acts)
        self.hostname = QLineEdit()
        save = QPushButton(tr("Rename"))
        save.clicked.connect(lambda: bg(lambda: B.set_hostname(self.hostname.text().strip()),
                                        lambda r: self.toast(tr("Saved") if r.ok else (r.err or r.out).strip()[:100])))
        h = QHBoxLayout()
        h.addWidget(self.hostname)
        h.addWidget(save)
        w = QWidget()
        w.setLayout(h)
        self.lay.addWidget(section(tr("Computer name")))
        self.add_card(row(tr("Hostname"), w, tr("Name visible to other devices on the network")))

    def refresh(self):
        import platform
        self.hostname.setText(platform.node())
        self.list.clear()
        me = B.current_user()
        for u in B.users():
            face = Path(u.home) / ".face.icon"
            ic = QIcon(str(face)) if face.exists() else icon("user-identity", "avatar-default")
            role = tr("Administrator") if u.admin else tr("Standard user")
            it = QListWidgetItem(ic, f"{u.name}  ({u.login})\n{role}" + ("  · " + tr("you") if u.login == me else ""))
            it.setData(Qt.UserRole, u)
            self.list.addItem(it)

    def _sel(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def add(self):
        d = UserDialog(self)
        if d.exec():
            bg(lambda: B.add_user(d.login.text(), d.full.text() or d.login.text(), d.pw.text(), d.admin.isChecked()),
               lambda r: (self.toast(tr("User added") if r.ok else tr("Failed: {e}", e=(r.err or "").strip()[:100])), self.refresh()))

    def toggle_admin(self):
        u = self._sel()
        if u:
            bg(lambda: B.set_admin(u.login, not u.admin), lambda r: self.refresh())

    def set_pw(self):
        u = self._sel()
        if not u:
            return
        pw, ok = QInputDialog.getText(self, tr("Set password…"), tr("New password for {u}:", u=u.login), QLineEdit.Password)
        if ok and pw:
            bg(lambda: B.set_user_password(u.login, pw), lambda r: self.toast(tr("Password changed") if r.ok else tr("Failed")))

    def delete(self):
        u = self._sel()
        if not u:
            return
        if u.login == B.current_user():
            self.toast(tr("You cannot delete your own account."))
            return
        box = QMessageBox(QMessageBox.Warning, tr("Delete user…"), tr("Delete account {u}?", u=u.login), parent=self)
        keep = box.addButton(tr("Delete account, keep files"), QMessageBox.AcceptRole)
        purge = box.addButton(tr("Delete account and files"), QMessageBox.DestructiveRole)
        cancel = box.addButton(tr("Cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() in (keep, purge):
            p = box.clickedButton() is purge
            bg(lambda: B.delete_user(u.login, p), lambda r: (self.toast(tr("User deleted") if r.ok else tr("Failed")), self.refresh()))


# ================================================================ Hasła
class PasswordsPage(Page):
    TITLE, SUBTITLE, ICON = "Passwords", "Change your password", "dialog-password"

    def build(self):
        f = QFormLayout()
        self.old, self.new, self.new2 = QLineEdit(), QLineEdit(), QLineEdit()
        for w in (self.old, self.new, self.new2):
            w.setEchoMode(QLineEdit.Password)
        self.strength = QProgressBar()
        self.strength.setRange(0, 4)
        self.hint = QLabel()
        self.hint.setObjectName("Subtitle")
        self.new.textChanged.connect(self._strength)
        f.addRow(tr("Current password:"), self.old)
        f.addRow(tr("New password:"), self.new)
        f.addRow(tr("Repeat password:"), self.new2)
        f.addRow(tr("Strength:"), self.strength)
        f.addRow("", self.hint)
        btn = QPushButton(tr("Change password"))
        btn.setObjectName("Accent")
        btn.clicked.connect(self.change)
        v = self.add_card(f)
        v.addWidget(btn, 0, Qt.AlignRight)
        tips = QLabel(tr("A good password has at least 12 characters and mixes letters, digits and symbols. "
                         "This password also unlocks the screen and authorises administrative actions."))
        tips.setWordWrap(True)
        tips.setObjectName("Subtitle")
        self.lay.addWidget(tips)

    def _strength(self, t):
        s, label = B.password_strength(t)
        self.strength.setValue(s)
        self.hint.setText(tr(label))

    def change(self):
        if self.new.text() != self.new2.text() or not self.new.text():
            self.toast(tr("Passwords do not match or are too short."))
            return
        old, new = self.old.text(), self.new.text()
        bg(lambda: B.change_own_password(old, new), self._done)

    def _done(self, res):
        ok, msg = res if isinstance(res, tuple) else (False, str(res))
        if ok:
            for w in (self.old, self.new, self.new2):
                w.clear()
            self.toast(tr("Password changed"))
        else:
            QMessageBox.warning(self, tr("Change password"), tr("Password was not changed.") + "\n" + msg)


# ================================================================ Aktualizacje
class UpdatesPage(Page):
    TITLE, SUBTITLE, ICON = "Updates", "System and application updates", "system-software-update"

    def build(self):
        self.info = QLabel()
        self.info.setObjectName("Section")
        self.last = QLabel()
        self.last.setObjectName("Subtitle")
        check = QPushButton(tr("Check for updates"))
        check.clicked.connect(self.check)
        self.install = QPushButton(tr("Install updates"))
        self.install.setObjectName("Accent")
        self.install.clicked.connect(self.do_install)
        h = QHBoxLayout()
        v = QVBoxLayout()
        v.addWidget(self.info)
        v.addWidget(self.last)
        h.addLayout(v, 1)
        h.addWidget(check)
        h.addWidget(self.install)
        self.add_card(h)
        self.progress = QProgressBar()
        self.progress.hide()
        self.lay.addWidget(self.progress)
        self.list = QListWidget()
        self.list.setMinimumHeight(220)
        self.add_card(self.list)
        self.auto = Switch(B.auto_updates_enabled())
        self.auto.toggled.connect(lambda on: bg(lambda: B.helper("auto-updates", "on" if on else "off")))
        self.lay.addWidget(section(tr("Automatic updates")))
        self.add_card(row(tr("Install security updates automatically"), self.auto,
                          tr("Uses unattended-upgrades from Ubuntu's security repository")))

    def refresh(self):
        ts = B.last_apt_update()
        self.last.setText(tr("Last checked: {t}", t=time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "—"))
        self._list()

    def _list(self):
        from nova_store.backends import Apt, Flatpak

        def work():
            res = [(n, v, "APT") for n, v in Apt.upgradable().items()]
            if Flatpak.available():
                res += [(n, v, "Flatpak") for n, v in Flatpak.upgradable().items()]
            return res

        def done(items):
            self.list.clear()
            items = items if isinstance(items, list) else []
            for n, v, s in items:
                self.list.addItem(f"{n}  →  {v}   ({s})")
            self.info.setText(tr("{n} updates available", n=len(items)) if items else tr("Your system is up to date."))
            self.install.setEnabled(bool(items))
        bg(work, done)

    def _task(self, cmds, label):
        self.progress.show()
        self.progress.setRange(0, 0)
        self.info.setText(label)
        self.t = Task(cmds, self)
        self.t.line.connect(self._line)
        self.t.finished.connect(lambda ok: (self.progress.hide(), self.toast(tr("Done") if ok else tr("Failed")), self.refresh()))
        self.t.start()

    def _line(self, text):
        if text.startswith("pmstatus:"):
            try:
                self.progress.setRange(0, 100)
                self.progress.setValue(int(float(text.split(":")[2])))
            except (IndexError, ValueError):
                pass

    def check(self):
        cmds = [privileged([B.HELPER, "apt-update"])]
        from nova_store.backends import Flatpak
        if Flatpak.available():
            cmds.append(["flatpak", "update", "--appstream", "-y"])
        self._task(cmds, tr("Checking for updates…"))

    def do_install(self):
        from nova_store.backends import Flatpak
        cmds = [privileged([B.HELPER, "apt-upgrade"])]
        if Flatpak.available():
            cmds.append(["flatpak", "update", "-y", "--noninteractive"])
        self._task(cmds, tr("Installing updates…"))


# ================================================================ Informacje
class AboutPage(Page):
    TITLE, SUBTITLE, ICON = "About this system", "Hardware and software information", "help-about"

    def build(self):
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon("novaos-logo").pixmap(96, 96))
        name = QLabel("<span style='font-size:26pt;font-weight:700'>NovaOS</span><br>"
                      f"<span style='opacity:.7'>{B.os_release().get('VERSION', '')}</span>")
        head.addWidget(logo)
        head.addWidget(name, 1)
        self.add_card(head)
        self.grid = QGridLayout()
        self.add_card(self.grid)
        copy = QPushButton(tr("Copy to clipboard"))
        copy.clicked.connect(self.copy)
        self.lay.addWidget(copy, 0, Qt.AlignRight)

    def refresh(self):
        if self.grid.count():
            return
        bg(B.system_info, self._fill)

    def _fill(self, info):
        if isinstance(info, Exception):
            return
        self.info = info
        for r, (k, v) in enumerate(info):
            kl = QLabel(tr(k))
            kl.setObjectName("Subtitle")
            vl = QLabel(v)
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.grid.addWidget(kl, r, 0, Qt.AlignTop)
            self.grid.addWidget(vl, r, 1)
        self.grid.setColumnStretch(1, 1)

    def copy(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(f"{k}: {v}" for k, v in getattr(self, "info", [])))
        self.toast(tr("Copied"))


# ================================================================ Aplikacje
class AppsPage(Page):
    TITLE, SUBTITLE, ICON = "Applications", "Installed apps, default apps and autostart", "preferences-desktop-default-applications"

    def build(self):
        self.lay.addWidget(section(tr("Default applications")))
        self.defaults = {}
        rows = []
        for kind, label in (("browser", tr("Web browser")), ("files", tr("File manager")), ("music", tr("Music")),
                            ("images", tr("Images")), ("text", tr("Text editor"))):
            cb = QComboBox()
            cb.setMinimumWidth(240)
            cb.activated.connect(lambda _i, k=kind, c=cb: B.set_default_app(k, c.currentData()))
            self.defaults[kind] = cb
            rows.append(row(label, cb))
        self.add_card(*rows)
        self.lay.addWidget(section(tr("Installed applications")))
        self.list = QListWidget()
        self.list.setIconSize(QSize(28, 28))
        self.list.setMinimumHeight(340)
        rm = QPushButton(tr("Uninstall…"))
        rm.clicked.connect(self.uninstall)
        store = QPushButton(tr("Open Nova Store"))
        store.clicked.connect(lambda: __import__("subprocess").Popen(["nova-store"]))
        h = QHBoxLayout()
        h.addWidget(rm)
        h.addWidget(store)
        h.addStretch(1)
        self.add_card(self.list, h)

    def refresh(self):
        apps = B.installed_apps()
        self.list.clear()
        for a in apps:
            it = QListWidgetItem(icon(a.icon, "application-x-executable"), a.name + ("  · Flatpak" if a.flatpak else ""))
            it.setData(Qt.UserRole, a)
            self.list.addItem(it)
        for kind, cb in self.defaults.items():
            cur = B.default_app(kind)
            cb.clear()
            for a in apps:
                cb.addItem(icon(a.icon), a.name, a.id + ".desktop")
                if a.id + ".desktop" == cur:
                    cb.setCurrentIndex(cb.count() - 1)

    def uninstall(self):
        it = self.list.currentItem()
        if not it:
            return
        a = it.data(Qt.UserRole)
        if a.flatpak:
            cmds = [["flatpak", "uninstall", "-y", "--noninteractive", a.id]]
        else:
            pkg = B.package_of(a.path)
            if not pkg:
                self.toast(tr("Unknown package"))
                return
            if pkg.startswith("novaos") or pkg in ("plasma-workspace", "systemsettings"):
                self.toast(tr("This is a core NovaOS component and cannot be removed."))
                return
            cmds = [privileged([B.HELPER, "apt-remove", pkg])]
        if confirm(self, tr("Uninstall"), tr("Uninstall {n}? Your personal files are not deleted.", n=a.name),
                   danger=True, yes=tr("Uninstall")):
            self.t = Task(cmds, self)
            self.t.finished.connect(lambda ok: (self.toast(tr("Removed") if ok else tr("Failed")), self.refresh()))
            self.t.start()


# ================================================================ Język
class LanguagePage(Page):
    TITLE, SUBTITLE, ICON = "Language & keyboard", "System language, formats and keyboard layouts", "preferences-desktop-locale"

    def build(self):
        self.lang = QComboBox()
        for loc, name in B.LANGUAGES.items():
            self.lang.addItem(name, loc)
        apply_user = QPushButton(tr("Apply for me"))
        apply_user.clicked.connect(self.apply_user)
        apply_sys = QPushButton(tr("Apply for the whole system"))
        apply_sys.clicked.connect(self.apply_system)
        h = QHBoxLayout()
        h.addWidget(apply_user)
        h.addWidget(apply_sys)
        h.addStretch(1)
        note = QLabel(tr("Changes take effect after you log out and back in."))
        note.setObjectName("Subtitle")
        self.add_card(row(tr("Language"), self.lang), h, note)
        self.lay.addWidget(section(tr("Keyboard layouts")))
        self.kb = QListWidget()
        self.kb.setMaximumHeight(170)
        add = QComboBox()
        add.addItem(tr("Add layout…"), "")
        for code, name in B.KEYBOARDS.items():
            add.addItem(name, code)
        add.activated.connect(lambda i: self._add_kb(add.itemData(i)) or add.setCurrentIndex(0))
        rm = QPushButton(tr("Remove"))
        rm.clicked.connect(self._rm_kb)
        h2 = QHBoxLayout()
        h2.addWidget(add)
        h2.addWidget(rm)
        h2.addStretch(1)
        hint = QLabel(tr("Switch layouts with Meta+Alt+K or from the panel."))
        hint.setObjectName("Subtitle")
        self.add_card(self.kb, h2, hint)

    def refresh(self):
        cur = B.user_language()
        i = self.lang.findData(cur)
        if i >= 0:
            self.lang.setCurrentIndex(i)
        self.kb.clear()
        for code in B.keyboard_layouts():
            it = QListWidgetItem(B.KEYBOARDS.get(code, code))
            it.setData(Qt.UserRole, code)
            self.kb.addItem(it)

    def _layouts(self):
        return [self.kb.item(i).data(Qt.UserRole) for i in range(self.kb.count())]

    def _add_kb(self, code):
        if code and code not in self._layouts():
            B.set_keyboard_layouts(self._layouts() + [code])
            self.refresh()

    def _rm_kb(self):
        it = self.kb.currentItem()
        if it and self.kb.count() > 1:
            B.set_keyboard_layouts([c for c in self._layouts() if c != it.data(Qt.UserRole)])
            self.refresh()

    def apply_user(self):
        B.set_user_language(self.lang.currentData())
        self.toast(tr("Saved – log out to apply"))

    def apply_system(self):
        loc = self.lang.currentData()
        code = loc[:2]

        def work():
            B.helper("language-pack", code)
            return B.set_system_language(loc)
        bg(work, lambda r: self.toast(tr("Saved – log out to apply") if getattr(r, "ok", False) else tr("Failed")))


# ================================================================ Data i czas
class DateTimePage(Page):
    TITLE, SUBTITLE, ICON = "Date & time", "Time zone and clock synchronisation", "preferences-system-time"

    def build(self):
        self.clock = QLabel()
        self.clock.setStyleSheet("font-size:28pt;font-weight:300")
        self.add_card(self.clock)
        self.ntp = Switch()
        self.ntp.toggled.connect(lambda on: bg(lambda: B.set_ntp(on), lambda r: self.refresh()))
        self.tz = QComboBox()
        self.tz.setEditable(True)
        self.tz.setMinimumWidth(260)
        self.tz.addItems(B.timezones())
        self.tz.activated.connect(lambda _i: bg(lambda: B.set_timezone(self.tz.currentText()),
                                                lambda r: (self.toast(tr("Time zone changed") if r.ok else tr("Failed")), self.refresh())))
        self.manual = QDateTimeEdit(QDateTime.currentDateTime())
        self.manual.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        set_btn = QPushButton(tr("Set"))
        set_btn.clicked.connect(lambda: bg(lambda: B.set_time(self.manual.dateTime().toString("yyyy-MM-dd HH:mm:ss")),
                                           lambda r: self.toast(tr("Saved") if r.ok else tr("Failed"))))
        h = QHBoxLayout()
        h.addWidget(self.manual)
        h.addWidget(set_btn)
        self.manual_w = QWidget()
        self.manual_w.setLayout(h)
        self.add_card(row(tr("Set time automatically"), self.ntp, tr("Synchronise with Internet time servers (NTP)")),
                      row(tr("Time zone"), self.tz), row(tr("Set time manually"), self.manual_w))
        from PySide6.QtCore import QTimer
        self.timer = QTimer(self, interval=1000, timeout=lambda: self.clock.setText(
            QDateTime.currentDateTime().toString("dddd, d MMMM yyyy   HH:mm:ss")))
        self.timer.start()

    def refresh(self):
        st = B.time_status()
        self.ntp.blockSignals(True)
        self.ntp.setChecked(st.get("NTP") == "yes")
        self.ntp.blockSignals(False)
        self.manual_w.setEnabled(st.get("NTP") != "yes")
        i = self.tz.findText(st.get("Timezone", ""))
        if i >= 0:
            self.tz.setCurrentIndex(i)


# ================================================================ Prywatność
class PrivacyPage(Page):
    TITLE, SUBTITLE, ICON = "Privacy & security", "Screen lock, history and firewall", "preferences-security"

    def build(self):
        auto, timeout, resume = B.lock_settings()
        self.auto = Switch(auto)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 120)
        self.timeout.setSuffix(" min")
        self.timeout.setValue(timeout)
        self.resume = Switch(resume)
        for w in (self.auto, self.resume):
            w.toggled.connect(self._save_lock)
        self.timeout.valueChanged.connect(self._save_lock)
        self.lay.addWidget(section(tr("Screen lock")))
        self.add_card(row(tr("Lock screen automatically"), self.auto), row(tr("After"), self.timeout),
                      row(tr("Lock after waking from sleep"), self.resume))
        self.lay.addWidget(section(tr("History")))
        self.recent = Switch(B.remember_recent())
        self.recent.toggled.connect(B.set_remember_recent)
        clear = QPushButton(tr("Clear recent files history"))
        clear.clicked.connect(lambda: (B.clear_recent(), self.toast(tr("History cleared"))))
        self.add_card(row(tr("Remember recently used files and apps"), self.recent,
                          tr("Shown in the Start menu under ‘Recent’")), clear)
        self.lay.addWidget(section(tr("Network protection")))
        self.fw = Switch()
        self.fw.toggled.connect(lambda on: bg(lambda: B.helper("firewall", "on" if on else "off"),
                                              lambda r: (self.toast(tr("Saved") if getattr(r, "ok", False) else tr("Failed")), self.refresh())))
        self.add_card(row(tr("Firewall"), self.fw, tr("Blocks unsolicited incoming connections (ufw)")))
        note = QLabel(tr("NovaOS does not collect telemetry. Crash reporting and usage statistics are not installed."))
        note.setWordWrap(True)
        note.setObjectName("Subtitle")
        self.lay.addWidget(note)

    def refresh(self):
        self.fw.blockSignals(True)
        self.fw.setChecked(B.firewall_active())
        self.fw.blockSignals(False)

    def _save_lock(self, *_):
        B.set_lock(self.auto.isChecked(), self.timeout.value(), self.resume.isChecked())
        self.timeout.setEnabled(self.auto.isChecked())


ALL_PAGES = [AppearancePage, DisplayPage, SoundPage, WifiPage, BluetoothPage, UsersPage, PasswordsPage,
             UpdatesPage, AboutPage, AppsPage, LanguagePage, DateTimePage, PrivacyPage]
