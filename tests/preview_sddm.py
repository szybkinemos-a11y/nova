#!/usr/bin/env python3
"""Podgląd motywu logowania SDDM bez SDDM: atrapa obiektów sddm/userModel/sessionModel/config
i render do PNG.  Użycie: python3 tests/preview_sddm.py out.png [ścieżka_motywu]"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import (QAbstractListModel, QByteArray, QModelIndex, QObject, Property, Qt, QTimer, QUrl,
                            Signal, Slot)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlPropertyMap
from PySide6.QtQuick import QQuickView

ROOT = Path(__file__).resolve().parent.parent
theme = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "packages/novaos-desktop/usr/share/sddm/themes/novaos"
assets = ROOT / "work/brand/sddm"


class Sddm(QObject):
    loginFailed = Signal()
    loginSucceeded = Signal()

    def __init__(self):
        super().__init__()
        self.attempts = []

    @Property(bool, constant=True)
    def canSuspend(self): return True

    @Property(bool, constant=True)
    def canReboot(self): return True

    @Property(bool, constant=True)
    def canPowerOff(self): return True

    @Slot(str, str, int)
    def login(self, user, password, session):
        self.attempts.append((user, password, session))
        QTimer.singleShot(50, self.loginFailed.emit)

    @Slot()
    def suspend(self): pass

    @Slot()
    def reboot(self): pass

    @Slot()
    def powerOff(self): pass


class ListModel(QAbstractListModel):
    def __init__(self, roles, rows, last_index=0, last_user=""):
        super().__init__()
        self._roles = {Qt.UserRole + 1 + i: QByteArray(r.encode()) for i, r in enumerate(roles)}
        self._names = roles
        self.rows = rows
        self._last_index, self._last_user = last_index, last_user

    def rowCount(self, parent=QModelIndex()): return len(self.rows)

    def roleNames(self): return self._roles

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        k = role - Qt.UserRole - 1
        return self.rows[index.row()][self._names[k]] if 0 <= k < len(self._names) else None

    @Property(int, constant=True)
    def lastIndex(self): return self._last_index

    @Property(str, constant=True)
    def lastUser(self): return self._last_user


class Keyboard(QObject):
    @Property(bool, constant=True)
    def capsLock(self): return False


app = QGuiApplication(sys.argv)
view = QQuickView()
users = ListModel(["name", "realName", "homeDir", "icon", "needsPassword"],
                  [{"name": "ola", "realName": "Ola Nowak", "homeDir": "/home/ola", "icon": "", "needsPassword": True},
                   {"name": "jan", "realName": "Jan Kowalski", "homeDir": "/home/jan", "icon": "", "needsPassword": True}],
                  0, "ola")
sessions = ListModel(["name", "file", "comment"], [{"name": "Plasma (Wayland)", "file": "plasma.desktop", "comment": ""}])
cfg = QQmlPropertyMap()
for k, v in {"background": str(assets / "background.png"), "logo": str(assets / "logo.png"), "accent": "#7B61FF", "blur": "0.65"}.items():
    cfg.insert(k, v)
sddm, kb = Sddm(), Keyboard()
ctx = view.rootContext()
for name, obj in (("sddm", sddm), ("userModel", users), ("sessionModel", sessions), ("config", cfg), ("keyboard", kb)):
    ctx.setContextProperty(name, obj)
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.resize(1600, 900)
view.setSource(QUrl.fromLocalFile(str(theme / "Main.qml")))
errors = view.errors()
if errors:
    for e in errors:
        print("QML ERROR:", e.toString())
    sys.exit(1)
view.show()
root = view.rootObject()


def shoot():
    view.grabWindow().save(sys.argv[1] if len(sys.argv) > 1 else "/tmp/sddm.png")
    # test logowania: wpisz hasło, wywołaj doLogin -> sddm.login(...) -> loginFailed -> komunikat
    pw = root.findChild(QObject, "password")
    pw.setProperty("text", "tajne")
    root.metaObject().invokeMethod(root, "doLogin")
    QTimer.singleShot(400, finish)


def finish():
    ok = sddm.attempts == [("ola", "tajne", 0)]
    print("login call:", sddm.attempts, "OK" if ok else "FAIL")
    view.grabWindow().save((sys.argv[1] if len(sys.argv) > 1 else "/tmp/sddm.png").replace(".png", "-failed.png"))
    app.exit(0 if ok else 1)


QTimer.singleShot(800, shoot)
sys.exit(app.exec())
