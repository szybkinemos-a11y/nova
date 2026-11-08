"""Walidacja plików konfiguracyjnych: Calamares (schematy), KDE, QML, desktop, JSON."""
import configparser
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CAL = ROOT / "packages/novaos-installer/etc/calamares"
SCHEMAS = Path(os.environ.get("CALAMARES_SCHEMAS", ROOT / "work/chroot/usr/lib/x86_64-linux-gnu/calamares/modules"))


def test_calamares_settings_sequence():
    s = yaml.safe_load((CAL / "settings.conf").read_text())
    assert s["branding"] == "novaos" and s["prompt-install"] is True
    exec_mods = s["sequence"][1]["exec"]
    assert exec_mods.index("unpackfs") < exec_mods.index("packages") < exec_mods.index("bootloader")
    for inst in s["instances"]:
        assert (CAL / "modules" / inst["config"]).is_file()


@pytest.mark.parametrize("conf", sorted((CAL / "modules").glob("*.conf")), ids=lambda p: p.name)
def test_calamares_module_yaml(conf):
    data = yaml.safe_load(conf.read_text())
    assert isinstance(data, dict), "module config must be a YAML mapping"
    schema = SCHEMAS / conf.stem / f"{conf.stem}.schema.yaml"
    if schema.exists():
        jsonschema = pytest.importorskip("jsonschema")
        jsonschema.validate(data, yaml.safe_load(schema.read_text()))


def test_partition_config_is_safe():
    p = yaml.safe_load((CAL / "modules/partition.conf").read_text())
    assert p["initialPartitioningChoice"] == "none"          # nic nie jest kasowane bez wyboru
    assert p["efi"]["mountPoint"] == "/boot/efi" and p["defaultPartitionTableType"] == "gpt"


def test_branding_desc():
    b = yaml.safe_load((CAL / "branding/novaos/branding.desc").read_text())
    for key in ("productLogo", "productIcon", "productWelcome"):
        assert b["images"][key].endswith(".png")
    assert (CAL / "branding/novaos" / b["slideshow"]).exists()


DESKTOP = ROOT / "packages/novaos-desktop"


@pytest.mark.parametrize("f", sorted((DESKTOP / "etc/xdg").glob("*rc")) + [DESKTOP / "etc/xdg/kdeglobals"],
                         ids=lambda p: p.name)
def test_kde_ini_parses(f):
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(f.read_text())
    assert cp.sections()


def test_color_schemes():
    for f in (DESKTOP / "usr/share/color-schemes").glob("*.colors"):
        cp = configparser.ConfigParser(strict=False, interpolation=None)
        cp.optionxform = str
        cp.read_string(f.read_text())
        for sec in ("Colors:Window", "Colors:View", "Colors:Button", "Colors:Selection", "General", "WM"):
            assert sec in cp, f"{f.name}: missing [{sec}]"
        assert cp["Colors:Selection"]["BackgroundNormal"] == "123,97,255"


def test_json_files():
    for f in list(ROOT.glob("packages/**/metadata.json")) + [ROOT / "apps/nova_store/catalog.json",
                                                              ROOT / "apps/novakit/locale/pl.json"]:
        json.loads(f.read_text())


@pytest.mark.parametrize("f", sorted((ROOT / "apps/desktop").glob("*.desktop")), ids=lambda p: p.name)
def test_desktop_files(f):
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(f.read_text())
    e = cp["Desktop Entry"]
    assert e["Type"] == "Application" and e["Exec"].split()[0] == f.stem and e["Icon"] == f.stem
    assert "Name" in e and "GenericName[pl]" in e


def test_qml_syntax():
    """qmllint (jeśli dostępny) – sprawdza składnię QML motywów."""
    import shutil
    qmllint = shutil.which("pyside6-qmllint") or shutil.which("qmllint6") or shutil.which("qmllint")
    if not qmllint:
        pytest.skip("qmllint niedostępny")
    files = [ROOT / "packages/novaos-desktop/usr/share/sddm/themes/novaos/Main.qml",
             ROOT / "packages/novaos-desktop/usr/share/plasma/look-and-feel/org.novaos.desktop/contents/splash/Splash.qml",
             ROOT / "packages/novaos-desktop/usr/share/plasma/plasmoids/org.novaos.controlcenter/contents/ui/main.qml",
             CAL / "branding/novaos/show.qml"]
    for f in files:
        r = subprocess.run([qmllint, "--max-warnings", "-1", "--disable-plugins", str(f)], capture_output=True, text=True)
        syntax_errors = [l for l in (r.stdout + r.stderr).splitlines() if "SyntaxError" in l or "Expected token" in l]
        assert not syntax_errors, f"{f.name}: {syntax_errors}"


def test_shell_scripts():
    import shutil
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck niedostępny")
    scripts = list((ROOT / "scripts").glob("*.sh")) + list((ROOT / "scripts/stages").glob("*.sh")) + \
        [ROOT / "packages/novaos-desktop/usr/bin/nova"]
    r = subprocess.run(["shellcheck", "-x", "-S", "warning", *map(str, scripts)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout


def test_nova_command_help():
    r = subprocess.run(["bash", str(ROOT / "packages/novaos-desktop/usr/bin/nova"), "help"],
                       capture_output=True, text=True, env={**os.environ, "LANG": "pl_PL.UTF-8"})
    assert r.returncode == 0 and "nova update" in r.stdout and "aktualizuj" in r.stdout


def test_plasma_layout_script():
    """layout.js wykonany z atrapą API Plasmy tworzy panel z menu Start, zadaniami, zasobnikiem itd."""
    import sys
    r = subprocess.run([sys.executable, str(ROOT / "tests/check_layout_js.py")], capture_output=True, text=True,
                       env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert r.returncode == 0 and "layout.js OK" in r.stdout, r.stdout + r.stderr


def test_sddm_theme_login_flow():
    """Motyw SDDM ładuje się bez błędów QML i wywołuje sddm.login() z wpisanym hasłem."""
    import sys
    import tempfile
    out = Path(tempfile.mkdtemp()) / "sddm.png"
    r = subprocess.run([sys.executable, str(ROOT / "tests/preview_sddm.py"), str(out)], capture_output=True, text=True,
                       timeout=60, env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"})
    if "work/brand" in r.stderr and not (ROOT / "work/brand").exists():
        pytest.skip("brak wygenerowanego brandingu (uruchom scripts/make-debs.sh)")
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout + r.stderr
    assert out.exists()
