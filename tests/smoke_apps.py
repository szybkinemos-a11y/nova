#!/usr/bin/env python3
"""Test dymny: tworzy okno każdej aplikacji Nova (bez ekranu), przetwarza zdarzenia
i zapisuje zrzut. Wynik != 0, jeśli którakolwiek aplikacja rzuci wyjątek.

Użycie: QT_QPA_PLATFORM=offscreen python3 tests/smoke_apps.py <katalog_zrzutów>
"""
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
os.environ.setdefault("NOVAOS_LANG", "pl")

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
app = QApplication(sys.argv)
from novakit import i18n, theme  # noqa: E402
i18n.load(os.environ["NOVAOS_LANG"])
theme.apply(app)
icon_dirs = [p for p in (ROOT / "work/brand/icons", Path("/usr/share/icons")) if p.exists()]
from PySide6.QtGui import QIcon  # noqa: E402
QIcon.setThemeSearchPaths([str(p) for p in icon_dirs] + QIcon.themeSearchPaths())
if not QIcon.themeName():
    QIcon.setThemeName("hicolor")


def pump(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def make(name):
    if name == "calculator":
        from nova_calculator.__main__ import Calculator
        w = Calculator()
        for k in "12×(3+4)−5":
            w.press(k) if k in "×−" else w._append(k)
        w.press("=")
        for k in ("sin", "3", "0", ")"):
            w.press(k)
        return w
    if name == "notes":
        from nova_notes.__main__ import Notes
        from nova_notes.storage import NoteStore
        st = NoteStore(Path("/tmp/nova-test/notes"))
        if not st.all():
            n = st.create("Lista zakupów")
            st.save(n, "# Zakupy\n\n- mleko\n- chleb\n- **kawa**\n")
            st.save(st.create("Pomysły na NovaOS"), "Centrum sterowania, motyw, ikony…")
        return Notes(st)
    if name == "monitor":
        from nova_monitor.__main__ import Monitor
        return Monitor()
    if name == "files":
        from nova_files.__main__ import Files
        return Files(str(ROOT))
    if name == "terminal":
        from nova_terminal.__main__ import Terminal
        w = Terminal(str(ROOT), ["/bin/bash", "--norc", "-i"])
        pump(0.5)
        w.term().write("PS1='\\[\\e[38;5;141m\\]nova@novaos\\[\\e[0m\\]:\\[\\e[38;5;75m\\]\\w\\[\\e[0m\\]$ '; clear; ls --color=always; echo -e '\\e[32mNova Terminal działa\\e[0m'\n".encode())
        return w
    if name == "browser":
        from nova_browser.__main__ import Browser
        return Browser()
    if name == "music":
        from nova_music.__main__ import Music
        return Music()
    if name == "gallery":
        from nova_gallery.__main__ import Gallery
        return Gallery(str(ROOT / "work/brand/logo") if (ROOT / "work/brand/logo").exists() else None)
    if name == "store":
        from nova_store.__main__ import Store
        return Store()
    if name == "settings":
        from nova_settings.__main__ import Settings
        return Settings()
    raise KeyError(name)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/nova-shots")
    out.mkdir(parents=True, exist_ok=True)
    names = sys.argv[2:] or ["calculator", "notes", "monitor", "files", "terminal", "browser",
                             "music", "gallery", "store", "settings"]
    failed = []
    for name in names:
        try:
            w = make(name)
            w.resize(1100, 700)
            w.show()
            pump(2.5 if name in ("browser", "terminal", "store", "monitor") else 1.0)
            w.grab().save(str(out / f"{name}.png"))
            if name == "settings":   # przejdź przez wszystkie strony ustawień
                for i in range(w.side.count()):
                    w.side.setCurrentRow(i)
                    pump(0.4)
                    w.grab().save(str(out / f"settings-{i:02d}.png"))
            print(f"OK   {name}")
            w.close()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            failed.append(name)
            print(f"FAIL {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
