"""Backend Nova Settings – wszystkie operacje na prawdziwych narzędziach systemowych.

Funkcje parse_* są czyste (bez efektów ubocznych) i pokryte testami.
"""
from __future__ import annotations

import grp
import json
import os
import pty
import pwd
import re
import select
import time
from dataclasses import dataclass
from pathlib import Path

from novakit.proc import Result, privileged, run, which

HELPER = "/usr/libexec/novaos/nova-helper"


def helper(*args: str, stdin: str | None = None) -> Result:
    return run(privileged([HELPER, *args]), timeout=1800, input_text=stdin)


# ================================================================ KDE config
def kread(file: str, group: str, key: str, default: str = "") -> str:
    r = run(["kreadconfig6", "--file", file, "--group", group, "--key", key, "--default", default])
    return r.out.strip() if r.ok else default


def kwrite(file: str, group: str, key: str, value: str) -> bool:
    groups = []
    for g in group.split("]["):
        groups += ["--group", g]
    return run(["kwriteconfig6", "--file", file, *groups, "--key", key, value]).ok


def kwin_reconfigure() -> None:
    run(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"])


# ================================================================ Wygląd
SCHEMES = {"dark": ("NovaDark", "Papirus-Dark"), "light": ("NovaLight", "Papirus")}
ACCENTS = {"Nova": "#7B61FF", "Violet": "#A855F7", "Blue": "#3B82F6", "Cyan": "#06B6D4",
           "Green": "#10B981", "Orange": "#F97316", "Pink": "#EC4899", "Red": "#EF4444"}


def current_theme() -> str:
    return "light" if "Light" in kread("kdeglobals", "General", "ColorScheme", "NovaDark") else "dark"


def set_theme(mode: str, accent: str | None = None) -> bool:
    scheme, icons = SCHEMES[mode]
    args = ["plasma-apply-colorscheme"]
    if accent:
        args += ["--accent-color", accent]
    ok = run(args + [scheme]).ok
    kwrite("kdeglobals", "Icons", "Theme", icons)
    run(["dbus-send", "--session", "--type=signal", "/KIconLoader", "org.kde.KIconLoader.iconChanged", "int32:0"])
    return ok


def set_accent(color: str) -> bool:
    return run(["plasma-apply-colorscheme", "--accent-color", color]).ok


def current_accent() -> str:
    raw = kread("kdeglobals", "General", "AccentColor", "123,97,255")
    try:
        r, g, b = (int(x) for x in raw.split(",")[:3])
        return f"#{r:02X}{g:02X}{b:02X}"
    except ValueError:
        return "#7B61FF"


def wallpapers() -> list[Path]:
    """Obrazy z /usr/share/wallpapers (pakiety Plasma) i ~/Obrazy/Tapety."""
    res = []
    for base in (Path("/usr/share/wallpapers"), Path.home() / ".local/share/wallpapers"):
        if not base.is_dir():
            continue
        for pkg in sorted(base.iterdir()):
            imgs = sorted((pkg / "contents/images").glob("*.*")) if (pkg / "contents/images").is_dir() else []
            if imgs:
                res.append(pkg)
            elif pkg.is_file() and pkg.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                res.append(pkg)
    return res


def wallpaper_preview(path: Path) -> Path:
    if path.is_dir():
        shot = path / "contents/screenshot.png"
        if shot.exists():
            return shot
        imgs = sorted((path / "contents/images").glob("*.*"))
        return imgs[0] if imgs else path
    return path


def set_wallpaper(path: Path) -> bool:
    return run(["plasma-apply-wallpaperimage", str(path)]).ok


def set_animation_speed(factor: float) -> None:
    kwrite("kdeglobals", "KDE", "AnimationDurationFactor", f"{factor:.3f}")


def set_effect(name: str, on: bool) -> None:
    kwrite("kwinrc", "Plugins", f"{name}Enabled", "true" if on else "false")
    kwin_reconfigure()


def effect_enabled(name: str, default: bool = True) -> bool:
    return kread("kwinrc", "Plugins", f"{name}Enabled", "true" if default else "false") == "true"


# ================================================================ Ekran
@dataclass
class Mode:
    id: str
    width: int
    height: int
    refresh: float

    @property
    def label(self) -> str:
        return f"{self.width} × {self.height} @ {self.refresh:.0f} Hz"


@dataclass
class Output:
    id: int
    name: str
    enabled: bool
    modes: list[Mode]
    current: str
    scale: float
    rotation: int


def parse_kscreen(text: str) -> list[Output]:
    data = json.loads(text)
    outs = []
    for o in data.get("outputs", []):
        if not o.get("connected", True):
            continue
        modes = [Mode(str(m["id"]), m["size"]["width"], m["size"]["height"], float(m.get("refreshRate", 0)))
                 for m in o.get("modes", [])]
        modes.sort(key=lambda m: (m.width * m.height, m.refresh), reverse=True)
        outs.append(Output(o.get("id", 0), o.get("name", "?"), o.get("enabled", True), modes,
                           str(o.get("currentModeId", "")), float(o.get("scale", 1.0)), int(o.get("rotation", 1))))
    return outs


def outputs() -> list[Output]:
    r = run(["kscreen-doctor", "-j"], timeout=10)
    if not r.ok:
        return []
    try:
        return parse_kscreen(r.out)
    except (ValueError, KeyError):
        return []


def apply_output(name: str, mode_id: str | None = None, scale: float | None = None) -> Result:
    args = ["kscreen-doctor"]
    if mode_id:
        args.append(f"output.{name}.mode.{mode_id}")
    if scale:
        args.append(f"output.{name}.scale.{scale:g}")
    return run(args, timeout=20)


# ================================================================ Dźwięk
@dataclass
class AudioDevice:
    name: str
    description: str
    volume: int
    muted: bool


def parse_pactl(text: str) -> list[AudioDevice]:
    devs = []
    for d in json.loads(text or "[]"):
        if d.get("name", "").endswith(".monitor"):
            continue
        vols = [int(str(c.get("value_percent", "0")).rstrip("%")) for c in (d.get("volume") or {}).values()]
        devs.append(AudioDevice(d["name"], d.get("description", d["name"]), max(vols) if vols else 0, bool(d.get("mute"))))
    return devs


def audio_devices(kind: str) -> tuple[list[AudioDevice], str]:
    """kind = 'sinks' (wyjścia) | 'sources' (wejścia) -> (urządzenia, domyślne)"""
    r = run(["pactl", "-f", "json", "list", kind])
    try:
        devs = parse_pactl(r.out) if r.ok else []
    except ValueError:
        devs = []
    default = run(["pactl", "get-default-" + kind[:-1]]).out.strip()
    return devs, default


def set_volume(kind: str, name: str, percent: int) -> None:
    run(["pactl", f"set-{kind[:-1]}-volume", name, f"{percent}%"])


def set_mute(kind: str, name: str, mute: bool) -> None:
    run(["pactl", f"set-{kind[:-1]}-mute", name, "1" if mute else "0"])


def set_default(kind: str, name: str) -> None:
    run(["pactl", f"set-default-{kind[:-1]}", name])


# ================================================================ Wi-Fi
@dataclass
class Network:
    ssid: str
    signal: int
    security: str
    active: bool


def split_nmcli(line: str) -> list[str]:
    """Dzieli linię nmcli -t po ':' z obsługą '\\:' i '\\\\'."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def parse_wifi(text: str) -> list[Network]:
    nets: dict[str, Network] = {}
    for line in text.splitlines():
        f = split_nmcli(line)
        if len(f) < 4 or not f[1]:
            continue
        n = Network(f[1], int(f[2] or 0), f[3] or "", f[0].strip() == "*")
        old = nets.get(n.ssid)
        if old is None or n.active or (n.signal > old.signal and not old.active):
            nets[n.ssid] = n
    return sorted(nets.values(), key=lambda n: (not n.active, -n.signal))


def wifi_enabled() -> bool:
    return run(["nmcli", "radio", "wifi"]).out.strip() == "enabled"


def wifi_set(on: bool) -> None:
    run(["nmcli", "radio", "wifi", "on" if on else "off"])


def wifi_scan() -> list[Network]:
    r = run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "auto"], timeout=30)
    return parse_wifi(r.out) if r.ok else []


def wifi_connect(ssid: str, password: str | None) -> Result:
    args = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    return run(args, timeout=60)


def wifi_disconnect(ssid: str) -> Result:
    return run(["nmcli", "con", "down", "id", ssid], timeout=30)


def wifi_forget(ssid: str) -> Result:
    return run(["nmcli", "con", "delete", "id", ssid], timeout=30)


# ================================================================ Bluetooth
@dataclass
class BtDevice:
    mac: str
    name: str
    paired: bool = False
    connected: bool = False


def parse_bt_devices(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^Device\s+([0-9A-F:]{17})\s+(.*)$", line.strip(), re.I)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def bt_available() -> bool:
    return bool(which("bluetoothctl")) and "Controller" in run(["bluetoothctl", "list"], timeout=5).out


def bt_powered() -> bool:
    return "Powered: yes" in run(["bluetoothctl", "show"], timeout=5).out


def bt_set_power(on: bool) -> Result:
    if on:
        run(["rfkill", "unblock", "bluetooth"])
    return run(["bluetoothctl", "power", "on" if on else "off"], timeout=10)


def bt_devices() -> list[BtDevice]:
    allp = parse_bt_devices(run(["bluetoothctl", "devices"], timeout=5).out)
    paired = {m for m, _ in parse_bt_devices(run(["bluetoothctl", "devices", "Paired"], timeout=5).out)}
    conn = {m for m, _ in parse_bt_devices(run(["bluetoothctl", "devices", "Connected"], timeout=5).out)}
    return [BtDevice(m, n, m in paired, m in conn) for m, n in allp]


def bt_scan(seconds: int = 8) -> None:
    run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], timeout=seconds + 5)


def bt_action(action: str, mac: str) -> Result:
    if action == "pair":
        r = run(["bluetoothctl", "--timeout", "20", "pair", mac], timeout=30)
        run(["bluetoothctl", "trust", mac])
        return r
    return run(["bluetoothctl", action, mac], timeout=30)


# ================================================================ Użytkownicy
@dataclass
class User:
    login: str
    name: str
    uid: int
    home: str
    admin: bool


def users() -> list[User]:
    sudo = set(grp.getgrnam("sudo").gr_mem) if "sudo" in {g.gr_name for g in grp.getgrall()} else set()
    res = []
    for p in pwd.getpwall():
        if 1000 <= p.pw_uid < 60000 and p.pw_shell not in ("/usr/sbin/nologin", "/bin/false"):
            res.append(User(p.pw_name, p.pw_gecos.split(",")[0] or p.pw_name, p.pw_uid, p.pw_dir, p.pw_name in sudo))
    return sorted(res, key=lambda u: u.uid)


def current_user() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def valid_login(login: str) -> bool:
    return bool(USER_RE.match(login))


def password_strength(pw: str) -> tuple[int, str]:
    """0..4 + opis; zgodne z typowymi wymaganiami (długość, klasy znaków)."""
    score = 0
    if len(pw) >= 8:
        score += 1
    if len(pw) >= 12:
        score += 1
    classes = sum(bool(re.search(p, pw)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w\s]"))
    score += classes >= 2
    score += classes >= 3
    labels = ["very weak", "weak", "fair", "good", "strong"]
    return min(score, 4), labels[min(score, 4)]


def add_user(login: str, full: str, password: str, admin: bool) -> Result:
    return helper("user-add", login, full, "1" if admin else "0", stdin=password + "\n")


def delete_user(login: str, purge: bool) -> Result:
    return helper("user-del", login, "purge" if purge else "keep")


def set_admin(login: str, admin: bool) -> Result:
    return helper("user-admin", login, "1" if admin else "0")


def set_user_password(login: str, password: str) -> Result:
    return helper("user-passwd", login, stdin=password + "\n")


def change_own_password(old: str, new: str, timeout: float = 20) -> tuple[bool, str]:
    """Zmiana własnego hasła przez `passwd` w pseudo-terminalu (wymaga starego hasła)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["LC_ALL"] = "C"
        os.execvp("passwd", ["passwd"])
    out, sent = "", {"cur": False, "new": False, "re": False}
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.5)
            if not r:
                continue
            try:
                chunk = os.read(fd, 1024).decode(errors="replace")
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            low = out.lower()
            if not sent["cur"] and "current password" in low:
                os.write(fd, (old + "\n").encode())
                sent["cur"] = True
                out = ""
            elif not sent["new"] and "new password" in low and "retype" not in low:
                os.write(fd, (new + "\n").encode())
                sent["new"] = True
                out = ""
            elif not sent["re"] and "retype" in low:
                os.write(fd, (new + "\n").encode())
                sent["re"] = True
    finally:
        _, status = os.waitpid(pid, 0)
        os.close(fd)
    ok = os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    msg = out.strip().splitlines()[-1] if out.strip() else ""
    return ok, msg


# ================================================================ Aktualizacje
def auto_updates_enabled() -> bool:
    try:
        text = Path("/etc/apt/apt.conf.d/20auto-upgrades").read_text()
    except OSError:
        return False
    return 'Unattended-Upgrade "1"' in text


def last_apt_update() -> float:
    p = Path("/var/lib/apt/periodic/update-success-stamp")
    alt = Path("/var/cache/apt/pkgcache.bin")
    for f in (p, alt):
        if f.exists():
            return f.stat().st_mtime
    return 0


# ================================================================ System
def os_release() -> dict[str, str]:
    res = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                res[k] = v.strip('"')
    except OSError:
        pass
    return res


def system_info() -> list[tuple[str, str]]:
    import platform

    import psutil
    osr = os_release()
    cpu = "?"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    gpu = ", ".join(l.split(": ", 1)[-1] for l in run(["lspci"]).out.splitlines()
                    if re.search(r"VGA|3D|Display", l)) or "?"
    disk = psutil.disk_usage("/")
    plasma = run(["plasmashell", "--version"]).out.strip().replace("plasmashell ", "") or "?"
    sb = run(["mokutil", "--sb-state"]).out.strip() or "?"
    try:
        model = Path("/sys/class/dmi/id/product_name").read_text().strip()
        vendor = Path("/sys/class/dmi/id/sys_vendor").read_text().strip()
    except OSError:
        model = vendor = ""
    from PySide6 import __version__ as pyside_version
    return [
        ("System", osr.get("PRETTY_NAME", "NovaOS")),
        ("Base", f"Ubuntu {osr.get('UBUNTU_VERSION_ID', '')} LTS ({osr.get('UBUNTU_CODENAME', '')})"),
        ("Kernel", platform.release()),
        ("Desktop", f"KDE Plasma {plasma} ({os.environ.get('XDG_SESSION_TYPE', '?')})"),
        ("Qt", pyside_version),
        ("Computer", f"{vendor} {model}".strip() or "?"),
        ("Processor", f"{cpu} × {psutil.cpu_count()}"),
        ("Graphics", gpu),
        ("Memory", f"{psutil.virtual_memory().total / 1024**3:.1f} GiB"),
        ("Disk", f"{disk.used / 1024**3:.0f} / {disk.total / 1024**3:.0f} GiB"),
        ("Firmware", ("UEFI" if os.path.isdir("/sys/firmware/efi") else "BIOS") + (f" · {sb}" if "SecureBoot" in sb else "")),
        ("Hostname", platform.node()),
    ]


def set_hostname(name: str) -> Result:
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$", name):
        return Result(2, "", "invalid hostname")
    return run(["hostnamectl", "set-hostname", name], timeout=60)


# ================================================================ Aplikacje
@dataclass
class DesktopApp:
    id: str
    name: str
    icon: str
    path: Path
    flatpak: bool


def parse_desktop(path: Path) -> dict[str, str]:
    data, section = {}, None
    lang = os.environ.get("LANG", "en")[:2]
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("["):
                section = line.strip()
                continue
            if section != "[Desktop Entry]" or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k == f"Name[{lang}]":
                data["Name_l"] = v
            elif k in ("Name", "Icon", "NoDisplay", "Type", "Hidden", "Exec", "OnlyShowIn"):
                data[k] = v
    except OSError:
        pass
    return data


def installed_apps() -> list[DesktopApp]:
    dirs = [(Path("/usr/share/applications"), False), (Path("/var/lib/flatpak/exports/share/applications"), True),
            (Path.home() / ".local/share/flatpak/exports/share/applications", True)]
    apps = {}
    for d, fp in dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.desktop"):
            e = parse_desktop(f)
            if e.get("Type") != "Application" or e.get("NoDisplay") == "true" or e.get("Hidden") == "true":
                continue
            apps[f.stem] = DesktopApp(f.stem, e.get("Name_l") or e.get("Name", f.stem), e.get("Icon", ""), f, fp)
    return sorted(apps.values(), key=lambda a: a.name.lower())


def package_of(path: Path) -> str | None:
    r = run(["dpkg-query", "-S", str(path)])
    return r.out.split(":", 1)[0].strip() if r.ok else None


DEFAULT_KINDS = {"browser": ["x-scheme-handler/http", "x-scheme-handler/https", "text/html"],
                 "files": ["inode/directory"], "music": ["audio/mpeg", "audio/flac", "audio/ogg"],
                 "images": ["image/png", "image/jpeg", "image/webp"], "text": ["text/plain"]}


def default_app(kind: str) -> str:
    return run(["xdg-mime", "query", "default", DEFAULT_KINDS[kind][0]]).out.strip()


def set_default_app(kind: str, desktop_id: str) -> None:
    for mime in DEFAULT_KINDS[kind]:
        run(["xdg-mime", "default", desktop_id, mime])


# ================================================================ Język i region
LANGUAGES = {"pl_PL.UTF-8": "Polski", "en_US.UTF-8": "English (US)", "en_GB.UTF-8": "English (UK)",
             "de_DE.UTF-8": "Deutsch", "fr_FR.UTF-8": "Français", "es_ES.UTF-8": "Español",
             "uk_UA.UTF-8": "Українська", "cs_CZ.UTF-8": "Čeština"}
KEYBOARDS = {"pl": "Polski (programisty)", "us": "English (US)", "gb": "English (UK)", "de": "Deutsch",
             "fr": "Français", "ua": "Українська", "cz": "Čeština"}


def user_language() -> str:
    return kread("plasma-localerc", "Formats", "LANG", os.environ.get("LANG", "pl_PL.UTF-8"))


def set_user_language(locale: str) -> None:
    kwrite("plasma-localerc", "Formats", "LANG", locale)
    kwrite("plasma-localerc", "Translations", "LANGUAGE", locale.split(".")[0] + ":" + locale[:2])


def set_system_language(locale: str) -> Result:
    return run(["localectl", "set-locale", f"LANG={locale}"], timeout=60)


def keyboard_layouts() -> list[str]:
    v = kread("kxkbrc", "Layout", "LayoutList", "pl,us")
    return [x for x in v.split(",") if x]


def set_keyboard_layouts(layouts: list[str]) -> None:
    kwrite("kxkbrc", "Layout", "LayoutList", ",".join(layouts))
    kwrite("kxkbrc", "Layout", "Use", "true")
    run(["dbus-send", "--session", "--type=signal", "--reply-timeout=100", "/Layouts",
         "org.kde.keyboard.reloadConfig"])


def parse_timedatectl(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def time_status() -> dict[str, str]:
    return parse_timedatectl(run(["timedatectl", "show"]).out)


def timezones() -> list[str]:
    r = run(["timedatectl", "list-timezones"])
    return r.out.split() if r.ok else ["Europe/Warsaw", "UTC"]


def set_timezone(tz: str) -> Result:
    return run(["timedatectl", "set-timezone", tz], timeout=60)


def set_ntp(on: bool) -> Result:
    return run(["timedatectl", "set-ntp", "true" if on else "false"], timeout=60)


def set_time(dt: str) -> Result:
    return run(["timedatectl", "set-time", dt], timeout=60)


# ================================================================ Prywatność
def lock_settings() -> tuple[bool, int, bool]:
    auto = kread("kscreenlockerrc", "Daemon", "Autolock", "true") == "true"
    timeout = int(kread("kscreenlockerrc", "Daemon", "Timeout", "5") or 5)
    resume = kread("kscreenlockerrc", "Daemon", "LockOnResume", "true") == "true"
    return auto, timeout, resume


def set_lock(auto: bool, timeout: int, resume: bool) -> None:
    kwrite("kscreenlockerrc", "Daemon", "Autolock", str(auto).lower())
    kwrite("kscreenlockerrc", "Daemon", "Timeout", str(timeout))
    kwrite("kscreenlockerrc", "Daemon", "LockOnResume", str(resume).lower())


RECENT_GROUP = "Plugin-org.kde.ActivityManager.Resources.Scoring"


def remember_recent() -> bool:
    return kread("kactivitymanagerd-pluginsrc", RECENT_GROUP, "what-to-remember", "0") != "2"


def set_remember_recent(on: bool) -> None:
    kwrite("kactivitymanagerd-pluginsrc", RECENT_GROUP, "what-to-remember", "0" if on else "2")


def clear_recent() -> None:
    for p in (Path.home() / ".local/share/RecentDocuments", ):
        if p.is_dir():
            for f in p.iterdir():
                f.unlink(missing_ok=True)
    xbel = Path.home() / ".local/share/recently-used.xbel"
    xbel.unlink(missing_ok=True)
    db = Path.home() / ".local/share/kactivitymanagerd/resources/database"
    if db.exists():
        run(["sqlite3", str(db), "DELETE FROM ResourceEvent; DELETE FROM ResourceScoreCache;"])


def firewall_active() -> bool:
    return run(["systemctl", "is-active", "ufw"]).out.strip() == "active" and \
        "ENABLED=yes" in (Path("/etc/ufw/ufw.conf").read_text() if Path("/etc/ufw/ufw.conf").exists() else "")
