"""Testy jednostkowe logiki aplikacji NovaOS (bez GUI)."""
import json
import math

import pytest


# ---------------------------------------------------------------- kalkulator
from nova_calculator.engine import CalcError, Engine, fmt


@pytest.mark.parametrize("expr,expected", [
    ("2+2", 4), ("12×(3+4)−5", 79), ("7÷2", 3.5), ("2^10", 1024), ("50%", 0.5), ("200×10%", 20),
    ("5!", 120), ("(2+1)!", 6), ("√(16)", 4), ("10 mod 3", 1), ("-3+1", -2), ("1,5×2", 3),
])
def test_calc_basic(expr, expected):
    assert Engine().evaluate(expr) == pytest.approx(expected)


def test_calc_trig_degrees_and_radians():
    e = Engine()
    assert e.evaluate("sin(30)") == pytest.approx(0.5)
    e.degrees = False
    assert e.evaluate("sin(π/2)") == pytest.approx(1)


def test_calc_ans_and_constants():
    e = Engine()
    e.evaluate("6×7")
    assert e.evaluate("ans+1") == 43
    assert e.evaluate("e") == pytest.approx(math.e)


@pytest.mark.parametrize("bad", ["1/0", "2+", "__import__('os')", "open('x')", "sqrt(-1)", "9^99999", "171!", ""])
def test_calc_rejects_unsafe_or_invalid(bad):
    with pytest.raises(CalcError):
        Engine().evaluate(bad)


def test_fmt():
    assert fmt(1234567) == "1 234 567"
    assert fmt(0.1 + 0.2) == "0.3"


# ---------------------------------------------------------------- notatki
from nova_notes.storage import NoteStore, safe_name


def test_notes_crud(tmp_path):
    st = NoteStore(tmp_path)
    n = st.create("Zakupy")
    st.save(n, "mleko\nchleb")
    assert [x.title for x in st.all()] == ["Zakupy"]
    assert st.all("chleb")[0].title == "Zakupy"
    n2 = st.create("Zakupy")
    assert n2.title == "Zakupy (2)"
    st.set_pinned(n2, True)
    assert st.all()[0].title == "Zakupy (2)" and st.all()[0].pinned
    st.set_pinned(n2, False)
    assert not n2.pinned
    renamed = st.rename(n, "Lista: sklep/dom")
    assert renamed.title == "Lista- sklep-dom" and renamed.read() == "mleko\nchleb"


def test_safe_name():
    assert safe_name('a/b\\c:d*e?"f<g>h|') == "a-b-c-d-e--f-g-h-"
    assert safe_name("   ") == "Notatka"


# ---------------------------------------------------------------- przeglądarka
from nova_browser.data import Bookmarks, History, to_url


@pytest.mark.parametrize("text,url", [
    ("kde.org", "https://kde.org"), ("https://x.pl/a", "https://x.pl/a"),
    ("localhost:8080", "http://localhost:8080"), ("192.168.1.1", "http://192.168.1.1"),
    ("jak zrobić pierogi", "https://duckduckgo.com/?q=jak+zrobi%C4%87+pierogi"), ("", "nova:newtab"),
])
def test_to_url(text, url):
    assert to_url(text) == url


def test_to_url_engine():
    assert to_url("linux", "Google") == "https://www.google.com/search?q=linux"


def test_bookmarks_and_history(tmp_path):
    b = Bookmarks(tmp_path)
    assert b.has("https://kde.org")
    assert b.toggle("https://example.com", "Ex") is True
    assert Bookmarks(tmp_path).has("https://example.com")
    assert b.toggle("https://example.com", "Ex") is False
    h = History(tmp_path)
    h.add("https://a.pl", "A")
    h.add("https://a.pl", "A2")
    h.add("nova:newtab", "x")
    h.add("https://b.pl/linux", "B")
    assert len(h.items) == 2 and h.items[0]["title"] == "A2"
    assert [i["url"] for i in h.search("linux")] == ["https://b.pl/linux"]


# ---------------------------------------------------------------- sklep
from nova_store.backends import load_catalog, parse_apt_search, parse_apt_upgradable, parse_columns


def test_catalog_valid():
    cats, apps = load_catalog()
    ids = {c["id"] for c in cats}
    assert len(apps) >= 30
    assert all(a.category in ids for a in apps)
    assert all(a.source in ("apt", "flatpak") for a in apps)
    assert len({a.key for a in apps}) == len(apps)


def test_apt_parsers():
    assert parse_apt_search("htop - interactive processes viewer\nbtop - x - y") == \
        [("htop", "interactive processes viewer"), ("btop", "x - y")]
    out = "Listing...\nfirefox/resolute-updates 140.1 amd64 [upgradable from: 140.0]\nbash/resolute 5.3-1 amd64 [upgradable from: 5.2]"
    assert parse_apt_upgradable(out) == {"firefox": "140.1", "bash": "5.3-1"}


def test_flatpak_columns():
    out = "org.gimp.GIMP\tGIMP\tImage editor\t3.0\tflathub\nshort\tline"
    assert parse_columns(out, 5) == [["org.gimp.GIMP", "GIMP", "Image editor", "3.0", "flathub"]]


# ---------------------------------------------------------------- ustawienia
from nova_settings import backend as B


def test_nmcli_split_and_wifi():
    assert B.split_nmcli(r"*:Dom\:5G:80:WPA2") == ["*", "Dom:5G", "80", "WPA2"]
    nets = B.parse_wifi("*:Dom:70:WPA2\n:Dom:90:WPA2\n:Kawiarnia:55:\n::40:WPA2")
    assert [n.ssid for n in nets] == ["Dom", "Kawiarnia"]
    assert nets[0].active and nets[0].signal == 70


def test_kscreen_parser():
    data = {"outputs": [{"id": 1, "name": "Virtual-1", "connected": True, "enabled": True, "currentModeId": "2",
                         "scale": 1.25, "rotation": 1,
                         "modes": [{"id": "1", "size": {"width": 1280, "height": 720}, "refreshRate": 60},
                                   {"id": "2", "size": {"width": 1920, "height": 1080}, "refreshRate": 59.96}]},
                        {"id": 2, "name": "HDMI-1", "connected": False, "modes": []}]}
    outs = B.parse_kscreen(json.dumps(data))
    assert len(outs) == 1 and outs[0].modes[0].label == "1920 × 1080 @ 60 Hz" and outs[0].scale == 1.25


def test_pactl_parser():
    data = [{"name": "alsa_output.pci", "description": "Głośniki", "mute": False,
             "volume": {"front-left": {"value_percent": "40%"}, "front-right": {"value_percent": "45%"}}},
            {"name": "x.monitor", "description": "Monitor", "mute": False, "volume": {}}]
    devs = B.parse_pactl(json.dumps(data))
    assert len(devs) == 1 and devs[0].volume == 45 and devs[0].description == "Głośniki"


def test_bt_and_timedatectl():
    assert B.parse_bt_devices("Device AA:BB:CC:DD:EE:FF Słuchawki JBL\nController x") == [("AA:BB:CC:DD:EE:FF", "Słuchawki JBL")]
    assert B.parse_timedatectl("Timezone=Europe/Warsaw\nNTP=yes")["Timezone"] == "Europe/Warsaw"


@pytest.mark.parametrize("pw,score", [("abc", 0), ("abcdefgh", 1), ("abcdefgh1", 2), ("Abcdefgh1!", 3), ("Abcdefgh1!xyz", 4)])
def test_password_strength(pw, score):
    assert B.password_strength(pw)[0] == score


@pytest.mark.parametrize("login,ok", [("anna", True), ("jan_kowalski-2", True), ("Root", False), ("1abc", False), ("a b", False)])
def test_login_validation(login, ok):
    assert B.valid_login(login) is ok


def test_desktop_parser(tmp_path):
    f = tmp_path / "x.desktop"
    f.write_text("[Desktop Entry]\nType=Application\nName=Files\nName[pl]=Pliki\nIcon=folder\n[Desktop Action a]\nName=Bad\n")
    d = B.parse_desktop(f)
    assert d["Name"] == "Files" and d["Icon"] == "folder"


# ---------------------------------------------------------------- inne
from novakit.proc import parse_percent, run


def test_parse_percent_and_run():
    assert parse_percent("Installing… [ 45%]") == 45
    assert parse_percent("no progress") is None
    assert run(["definitely-not-a-command-xyz"]).code == 127
    assert run(["echo", "ok"]).out.strip() == "ok"


def test_translations_complete():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(root / "scripts/extract-strings.py"), "pl"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_music_library(tmp_path):
    from nova_music.library import fmt_time, read_track, scan
    (tmp_path / "Artysta - Utwór.mp3").write_bytes(b"\x00" * 10)
    (tmp_path / "notes.txt").write_text("x")
    tracks = scan([tmp_path])
    assert len(tracks) == 1 and tracks[0].artist == "Artysta" and tracks[0].display_title == "Utwór"
    assert fmt_time(3725) == "1:02:05" and fmt_time(65) == "1:05"


def test_helper_rejects_non_root():
    import subprocess
    from pathlib import Path
    helper = Path(__file__).resolve().parent.parent / "apps/system/nova-helper"
    src = helper.read_text()
    ns = {"__name__": "nova_helper_test"}
    exec(compile(src, str(helper), "exec"), ns)
    assert ns["PKG_RE"].match("libreoffice-writer") and not ns["PKG_RE"].match("foo; rm -rf /")
    assert ns["USER_RE"].match("anna") and not ns["USER_RE"].match("../etc")


def test_calculator_window_after_equals():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nova_calculator.__main__ import Calculator
    w = Calculator()
    for k in "2+3":
        w._append(k)
    w.press("=")
    w.press("sin"); w._append("30"); w._append(")"); w.press("=")
    assert w.display.text() == "0.5"
    w.press("+"); w._append("1"); w.press("=")
    assert w.display.text() == "1.5"
