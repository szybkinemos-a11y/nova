# NovaOS

**NovaOS** to system operacyjny oparty na **Ubuntu 26.04 LTS** („Resolute Raccoon”) z pulpitem
**KDE Plasma 6** na Waylandzie. Ma własny wygląd, branding, 10 aplikacji, ekran logowania,
ekran rozruchu i instalator. Skrypty w tym repozytorium budują z niego uruchamialny obraz
**`NovaOS.iso`**.

| | |
|---|---|
| Baza | Ubuntu 26.04 LTS (wsparcie do 2029), jądro Linux 7.0 |
| Pulpit | KDE Plasma 6.6 (Wayland), KWin z rozmyciem, animacjami i zaokrąglonymi rogami |
| Architektura | x86_64 (amd64) |
| Rozruch | UEFI (z Secure Boot: podpisany shim + GRUB) i BIOS, tablica GPT |
| Instalator | Calamares 3.3 z brandingiem NovaOS |
| Pakiety | APT (repozytoria Ubuntu) + Flatpak (Flathub), **bez snapów** |
| Języki | polski (domyślny), angielski |
| Motyw | ciemny (Nova Dark), akcent fioletowo-niebieski `#7B61FF` |

## Szybki start

```bash
# Ubuntu/Debian jako host:
sudo ./scripts/install-host-deps.sh
sudo ./scripts/build-iso.sh            # ok. 20–40 min, potrzeba ~25 GB miejsca

# Arch / Fedora / inny Linux – w kontenerze (zalecane):
sudo ./scripts/docker-build.sh         # Docker albo Podman

# Wynik:
ls out/NovaOS.iso out/NovaOS.iso.sha256
```

Uruchomienie i instalacja:

```bash
./scripts/test-qemu.sh                 # podgląd w QEMU (UEFI)
./scripts/test-qemu.sh --install       # z wirtualnym dyskiem 32 GB – test instalatora
sudo ./scripts/write-usb.sh /dev/sdX   # nagranie na pendrive (z potwierdzeniem)
```

VirtualBox / VMware: utwórz maszynę „Ubuntu (64-bit)”, 4 GB RAM, 2+ CPU, dysk 25+ GB,
**włącz EFI** (VirtualBox: Ustawienia → System → Włącz EFI), grafika VMSVGA z akceleracją 3D,
podłącz `NovaOS.iso` jako napęd optyczny. Szczegóły: [docs/BUILD.md](docs/BUILD.md).

## Co jest w systemie

**Pulpit:** pływający pasek zadań na dole (dopasowany do zawartości), menu Start z logo NovaOS
(wszystkie aplikacje, wyszukiwarka, ostatnio używane, profil użytkownika, uśpij / uruchom ponownie /
wyłącz), przypięte aplikacje, zasobnik systemowy, **Centrum sterowania Nova** (Wi‑Fi, Bluetooth,
tryb ciemny, światło nocne, głośność), zegar z kalendarzem, powiadomienia, rozmycie
i przezroczystość, animacje otwierania/zamykania okien, zaokrąglone rogi z gradientowym obrysem.

**Aplikacje Nova** (Python 3 + Qt 6 / PySide6, wspólna biblioteka `novakit`):

| Aplikacja | Co robi naprawdę |
|---|---|
| Nova Browser | Chromium (QtWebEngine): karty, zakładki, historia, pobieranie, tryb prywatny, wyszukiwanie na stronie, PDF, pytania o uprawnienia |
| Nova Files | miejsca i dyski, widok ikon/listy, kopiuj/wytnij/wklej w tle, kosz, właściwości, terminal tutaj |
| Nova Terminal | prawdziwy terminal: pty + emulacja xterm‑256color (pyte), karty, schowek, przewijanie, zoom |
| Nova Settings | 13 sekcji: wygląd, ekran, dźwięk, Wi‑Fi, Bluetooth, użytkownicy, hasła, aktualizacje, informacje, aplikacje, język, data i czas, prywatność |
| Nova Store | polecane i kategorie, wyszukiwanie APT + Flathub, instalacja/odinstalowanie/aktualizacje z postępem |
| Nova Music | biblioteka z tagami (mutagen), okładki, losowo, powtarzanie, kolejka |
| Nova Gallery | miniatury w tle, zoom, obrót, pokaz slajdów, pełny ekran, ustaw jako tapetę, kosz |
| Nova Calculator | standardowy i naukowy, bezpieczny parser (bez `eval`), historia |
| Nova Notes | notatki Markdown w `~/Dokumenty/Notatki`, autozapis, przypinanie, podgląd, druk/PDF |
| Nova Monitor | wykresy CPU/RAM/sieć/dysk, rdzenie, procesy (sortowanie, filtr, zakończ), informacje |

**Terminal:** standardowe polecenia (`ls`, `cd`, `mkdir`, `rm`, `sudo`, `apt`, `ping`, `clear`…),
`fastfetch` / `neofetch` z logo NovaOS oraz polecenie **`nova`**:

```
nova                 informacje o systemie       nova theme dark|light
nova update          APT + Flatpak + firmware     nova accent #7B61FF
nova search/install/remove <pakiet>               nova wallpaper <plik>
nova doctor          diagnostyka                  nova clean
```

**Branding:** logo (gwiazda „nova” na orbicie), tapety jasna i ciemna (Plasma przełącza je razem
z motywem), 12 ikon, motyw globalny Plasma „NovaOS”, schematy kolorów Nova Dark/Light, ekran
rozruchu Plymouth, ekran ładowania po zalogowaniu, ekran logowania SDDM, motyw menu GRUB,
pokaz slajdów instalatora. Wszystkie grafiki generuje kod (`branding/generate.py`).

## Struktura projektu

```
NovaOS/
├── build.conf               # wszystkie ustawienia budowania (wersja, mirror, język…)
├── scripts/
│   ├── build-iso.sh         # główny skrypt: bootstrap → packages → novaos → finalize → squashfs → iso
│   ├── stages/*.sh          # poszczególne etapy (wznawialne)
│   ├── make-debs.sh         # pakiety novaos-desktop / novaos-apps / novaos-installer
│   ├── docker-build.sh      # budowanie w kontenerze
│   ├── test-qemu.sh, write-usb.sh, install-host-deps.sh, extract-strings.py
├── config/
│   ├── packages/*.list      # listy pakietów Ubuntu (base, desktop, apps, installer, remove)
│   ├── apt/                 # blokada snapd, opcje APT
│   └── grub/grub.cfg        # menu nośnika live
├── packages/
│   ├── novaos-desktop/      # branding, motyw Plasma, SDDM, Plymouth, GRUB, KWin, polecenie nova
│   ├── novaos-apps/         # metadane pakietu aplikacji
│   └── novaos-installer/    # Calamares: konfiguracja, branding, slajdy, powitanie live
├── apps/                    # kod aplikacji (novakit + nova_*), pliki .desktop, nova-helper + polkit
├── branding/generate.py     # logo, ikony, tapety, grafiki rozruchu
├── tests/                   # pytest, test dymny aplikacji, podgląd ekranu logowania
└── docs/                    # architektura, budowanie, aplikacje, testy
```

## Dokumentacja

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) – jak zbudowany jest system i dlaczego
- [docs/BUILD.md](docs/BUILD.md) – budowanie ISO, VirtualBox, VMware, pendrive, instalacja
- [docs/APPS.md](docs/APPS.md) – aplikacje, skróty klawiszowe, rozwój
- [docs/TESTING.md](docs/TESTING.md) – testy automatyczne i lista kontrolna

## Licencja

Kod NovaOS: GPL-3.0-or-later. Grafiki: CC BY-SA 4.0. Pakiety Ubuntu zachowują własne licencje.
