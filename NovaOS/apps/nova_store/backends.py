"""Źródła aplikacji Nova Store: APT (repozytoria Ubuntu) i Flatpak (Flathub).

Odczyty wykonujemy bez uprawnień; instalacja/usuwanie APT idzie przez
pkexec + nova-helper, a Flatpak sam pyta o autoryzację przez polkit.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from novakit.proc import privileged, run, which

HELPER = "/usr/libexec/novaos/nova-helper"
FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
APPSTREAM_ICONS = [Path("/var/lib/flatpak/appstream/flathub/x86_64/active/icons/128x128"),
                   Path.home() / ".local/share/flatpak/appstream/flathub/x86_64/active/icons/128x128"]


@dataclass
class App:
    id: str
    source: str            # "apt" | "flatpak"
    name: str
    summary: str = ""
    category: str = ""
    version: str = ""
    installed: bool = False
    update: str = ""       # nowa wersja, jeśli jest aktualizacja
    featured: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.id}"

    def icon_path(self) -> str | None:
        if self.source == "flatpak":
            for d in APPSTREAM_ICONS + [Path("/var/lib/flatpak/exports/share/icons/hicolor/128x128/apps")]:
                p = d / f"{self.id}.png"
                if p.is_file():
                    return str(p)
            svg = Path("/var/lib/flatpak/exports/share/icons/hicolor/scalable/apps") / f"{self.id}.svg"
            if svg.is_file():
                return str(svg)
        return None


def load_catalog() -> tuple[list[dict], list[App]]:
    data = json.loads((Path(__file__).with_name("catalog.json")).read_text(encoding="utf-8"))
    apps = [App(a["id"], a["source"], a["name"], a.get("summary", ""), a.get("category", ""),
                featured=a.get("featured", False)) for a in data["apps"]]
    return data["categories"], apps


# ---------------------------------------------------------------- APT
def parse_apt_search(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        if " - " in line:
            name, desc = line.split(" - ", 1)
            out.append((name.strip(), desc.strip()))
    return out


def parse_apt_upgradable(text: str) -> dict[str, str]:
    """'pakiet/resolute-updates 1.2 amd64 [upgradable from: 1.1]' -> {pakiet: 1.2}"""
    res = {}
    for line in text.splitlines():
        m = re.match(r"^([^/\s]+)/\S+\s+(\S+)\s+\S+\s+\[upgradable from", line)
        if m:
            res[m.group(1)] = m.group(2)
    return res


class Apt:
    name = "apt"

    @staticmethod
    def available() -> bool:
        return bool(which("apt-get"))

    @staticmethod
    def installed_versions(names: list[str]) -> dict[str, str]:
        if not names:
            return {}
        r = run(["dpkg-query", "-W", "-f=${Package}\t${Status}\t${Version}\n", *names])
        res = {}
        for line in r.out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[1].endswith("installed") and "not-installed" not in parts[1]:
                res[parts[0]] = parts[2]
        return res

    @staticmethod
    def search(query: str, limit: int = 40) -> list[App]:
        r = run(["apt-cache", "search", "--names-only", query], timeout=30)
        pairs = parse_apt_search(r.out)[:limit]
        inst = Apt.installed_versions([p for p, _ in pairs])
        return [App(n, "apt", n, d, installed=n in inst, version=inst.get(n, "")) for n, d in pairs]

    @staticmethod
    def upgradable() -> dict[str, str]:
        return parse_apt_upgradable(run(["apt", "list", "--upgradable"], timeout=60).out)

    @staticmethod
    def install_cmd(names: list[str]) -> list[list[str]]:
        return [privileged([HELPER, "apt-install", *names])]

    @staticmethod
    def remove_cmd(names: list[str]) -> list[list[str]]:
        return [privileged([HELPER, "apt-remove", *names])]

    @staticmethod
    def update_cmd() -> list[list[str]]:
        return [privileged([HELPER, "apt-update"]), privileged([HELPER, "apt-upgrade"])]


# ---------------------------------------------------------------- Flatpak
def parse_columns(text: str, n: int) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= n and parts[0] and not parts[0].startswith("Application ID"):
            rows.append(parts[:n])
    return rows


class Flatpak:
    name = "flatpak"

    @staticmethod
    def available() -> bool:
        return bool(which("flatpak"))

    @staticmethod
    def has_flathub() -> bool:
        return "flathub" in run(["flatpak", "remotes", "--columns=name"]).out.split()

    @staticmethod
    def add_flathub_cmd() -> list[list[str]]:
        return [["flatpak", "remote-add", "--system", "--if-not-exists", "flathub", FLATHUB_URL],
                ["flatpak", "update", "--appstream", "-y"]]

    @staticmethod
    def installed() -> dict[str, tuple[str, str]]:
        r = run(["flatpak", "list", "--app", "--columns=application,name,version"])
        return {a: (n, v) for a, n, v in parse_columns(r.out, 3)}

    @staticmethod
    def search(query: str, limit: int = 40) -> list[App]:
        r = run(["flatpak", "search", "--columns=application,name,description,version,remotes", query], timeout=40)
        inst = Flatpak.installed()
        apps = []
        for a, n, d, v, remotes in parse_columns(r.out, 5)[:limit]:
            apps.append(App(a, "flatpak", n, d, version=v, installed=a in inst, extra={"remote": remotes}))
        return apps

    @staticmethod
    def upgradable() -> dict[str, str]:
        r = run(["flatpak", "remote-ls", "--updates", "--app", "--columns=application,version"], timeout=60)
        return {a: v for a, v in parse_columns(r.out, 2)}

    @staticmethod
    def install_cmd(ids: list[str]) -> list[list[str]]:
        return [["flatpak", "install", "-y", "--noninteractive", "flathub", *ids]]

    @staticmethod
    def remove_cmd(ids: list[str]) -> list[list[str]]:
        return [["flatpak", "uninstall", "-y", "--noninteractive", *ids]]

    @staticmethod
    def update_cmd() -> list[list[str]]:
        return [["flatpak", "update", "-y", "--noninteractive"]]


BACKENDS = {"apt": Apt, "flatpak": Flatpak}


def refresh_state(apps: list[App]) -> None:
    """Uzupełnia flagi zainstalowania/wersje dla listy aplikacji z katalogu."""
    apt_names = [a.id for a in apps if a.source == "apt"]
    apt_inst = Apt.installed_versions(apt_names) if Apt.available() else {}
    fp_inst = Flatpak.installed() if Flatpak.available() else {}
    for a in apps:
        if a.source == "apt":
            a.installed = a.id in apt_inst
            a.version = apt_inst.get(a.id, a.version)
        else:
            a.installed = a.id in fp_inst
            if a.installed:
                a.version = fp_inst[a.id][1]


def launch_cmd(app: App) -> list[str] | None:
    if app.source == "flatpak":
        return ["flatpak", "run", app.id]
    desktop = Path(f"/usr/share/applications/{app.id}.desktop")
    if desktop.exists() and which("gtk-launch"):
        return ["gtk-launch", app.id]
    return [app.id] if which(app.id) else None
