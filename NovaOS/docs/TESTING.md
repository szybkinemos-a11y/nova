# Testy NovaOS

## Automatyczne

```bash
make test        # pytest: logika aplikacji + walidacja konfiguracji
make smoke       # uruchamia każdą aplikację bez ekranu i zapisuje zrzuty do out/screenshots
QT_QUICK_BACKEND=software python3 tests/preview_sddm.py out/sddm.png   # ekran logowania z atrapą SDDM
```

| Plik | Zakres |
|---|---|
| `tests/test_logic.py` | kalkulator (w tym odrzucanie niebezpiecznych wyrażeń), notatki, URL/zakładki/historia przeglądarki, katalog i parsery sklepu (apt, flatpak), parsery ustawień (nmcli, kscreen-doctor, pactl, bluetoothctl, timedatectl), siła haseł, walidacja loginów, biblioteka muzyki, walidacja w nova-helper, kompletność tłumaczeń |
| `tests/test_configs.py` | Calamares: kolejność modułów, bezpieczne partycjonowanie, **walidacja względem schematów JSON z pakietu calamares**, branding; pliki KDE (INI), schematy kolorów, JSON, `.desktop`, składnia QML (qmllint), shellcheck wszystkich skryptów, polecenie `nova` |
| `tests/smoke_apps.py` | tworzy okna 10 aplikacji (i 13 stron ustawień), wykonuje akcje (obliczenia, polecenia w terminalu), zapisuje zrzuty |
| `tests/preview_sddm.py` | ładuje motyw SDDM z atrapą API `sddm`/`userModel`, sprawdza wywołanie logowania i reakcję na błędne hasło |

## Lista kontrolna na maszynie wirtualnej

- [ ] GRUB: menu NovaOS (UEFI i BIOS), „Sprawdź nośnik” przechodzi
- [ ] Plymouth: logo NovaOS i pasek postępu
- [ ] Sesja live: automatyczne logowanie, okno „Wypróbuj / Zainstaluj”, ikona instalatora
- [ ] Pulpit: tapeta, pływający panel, menu Start (wyszukiwanie, ostatnie, zasilanie), Centrum sterowania
- [ ] Aplikacje Nova uruchamiają się z menu; Terminal: `nova`, `fastfetch`, `sudo apt update`, `ping -c3 ubuntu.com`
- [ ] Nova Store: wyszukanie i instalacja np. `htop` (APT) oraz Firefox (Flathub)
- [ ] Nova Settings: przełączenie motywu jasny/ciemny, akcent, tapeta, rozdzielczość
- [ ] Instalacja na pusty dysk (UEFI, GPT) → restart → ekran logowania NovaOS → logowanie
- [ ] Po instalacji: brak pakietów `calamares`, `casper`; `nova doctor` bez błędów; `swapon` pokazuje zram

## Wyniki weryfikacji (8.11.2026, środowisko budowania bez KVM)

| Test | Wynik |
|---|---|
| `pytest tests/` | 100 / 100 |
| Budowanie ISO (Ubuntu 26.04, Plasma 6.6.6, jądro 7.0, efekt zaokrąglonych rogów z kompilacji) | `NovaOS.iso` ≈ 2,3 GB |
| Struktura ISO | El Torito BIOS + UEFI, GPT z partycją EFI, podpisany shim + GRUB (Secure Boot) |
| QEMU UEFI (emulacja programowa) | menu GRUB z motywem → Plymouth NovaOS → automatyczne logowanie → sesja KWin/Wayland → okno „Witaj w NovaOS” z zaokrąglonymi rogami i obrysem |
| 10 aplikacji w zbudowanym systemie (Python 3.14, PySide6 6.10, offscreen) | wszystkie OK, interfejs po polsku |
| `plasmashell` w zbudowanym systemie (KWin `--virtual`) | układ panelu NovaOS ładuje się, ulubione menu Start rozpoznane |
| Ekran logowania (atrapa API SDDM) | ładowanie bez błędów QML, logowanie i komunikat o błędnym haśle |

Uwaga: bez KVM pulpit Plasmy w QEMU startuje bardzo długo (renderowanie programowe na emulowanym CPU).
Pełny test pulpitu i instalatora najlepiej robić w VirtualBox/VMware lub QEMU z KVM.
