# Aplikacje NovaOS

Wszystkie aplikacje to Python 3 + Qt 6 (PySide6 z repozytorium Ubuntu), zainstalowane
w `/usr/lib/novaos/python`, uruchamiane poleceniami `nova-*`. Wspólna biblioteka **novakit**:

| Moduł | Rola |
|---|---|
| `theme.py` | kolory ze schematu Plasma + zaokrąglenia, panel boczny, karty, akcent; paleta Nova poza KDE |
| `i18n.py` | `tr("…")`: teksty po angielsku w kodzie, katalog `locale/pl.json` (389 tekstów) |
| `proc.py` | `run()` (bez wyjątków), `Task` (asynchroniczne polecenia z postępem), `privileged()` → pkexec |
| `widgets.py` | `Sidebar`, `SearchField`, `Toast`, `confirm()` (domyślnie „Anuluj”), `notify()` (D-Bus) |
| `config.py` | `Store` – ustawienia w `~/.config/novaos/*.json` (zapis atomowy), katalogi XDG |

## Skróty klawiszowe

| Aplikacja | Skróty |
|---|---|
| Browser | Ctrl+T/W karta, Ctrl+L adres, Ctrl+D zakładka, Ctrl+F szukaj, Ctrl+Shift+N prywatne, Ctrl±/0 zoom, F11 |
| Files | Ctrl+C/X/V, Del kosz, Shift+Del trwale, F2 nazwa, Ctrl+H ukryte, Ctrl+Shift+N folder, Alt+←/→/↑ |
| Terminal | Ctrl+Shift+C/V, Ctrl+Shift+T/W karta, Shift+PgUp/PgDn historia, Ctrl±/0 font |
| Gallery | ←/→, +/−/0, R obrót, Del, F11, Esc |
| Calculator | klawiatura numeryczna, Enter, Backspace, Esc |
| Notes | Ctrl+N nowa, Ctrl+S zapisz, Ctrl+F szukaj |
| Music | Spacja, Ctrl+←/→ |

## Nova Settings – co wywołuje każda sekcja

| Sekcja | Narzędzie systemowe |
|---|---|
| Wygląd | `plasma-apply-colorscheme`, `plasma-apply-wallpaperimage`, `kwriteconfig6` (kwinrc) |
| Ekran | `kscreen-doctor` (z automatycznym przywróceniem po 15 s), światło nocne KWin |
| Dźwięk | `pactl` (PipeWire) |
| Wi‑Fi | `nmcli` |
| Bluetooth | `bluetoothctl`, `rfkill` |
| Użytkownicy / Hasła | `nova-helper user-*` (useradd, chpasswd, gpasswd), `passwd` w pty |
| Aktualizacje | `nova-helper apt-update/apt-upgrade`, `flatpak update`, unattended-upgrades |
| Informacje | `/etc/os-release`, `/proc`, `lspci`, `mokutil`, psutil |
| Aplikacje | pliki `.desktop`, `dpkg -S`, `xdg-mime` |
| Język | `plasma-localerc`, `kxkbrc`, `localectl`, pakiety językowe |
| Data i czas | `timedatectl` |
| Prywatność | `kscreenlockerrc`, KActivityManager, `ufw` |

## Rozwój

```bash
cd apps
python3 -m nova_calculator          # uruchom dowolną aplikację ze źródeł
NOVAOS_LANG=en python3 -m nova_settings
NOVAOS_THEME=light NOVAOS_FORCE_PALETTE=1 python3 -m nova_notes
python3 ../scripts/extract-strings.py pl   # brakujące tłumaczenia
```
Po zmianie aplikacji: `sudo ./scripts/build-iso.sh --from novaos`.
