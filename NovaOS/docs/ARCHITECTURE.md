# Architektura NovaOS

## Założenia

1. **Prawdziwy system, nie nakładka-atrapa.** NovaOS to Ubuntu 26.04 LTS z własną warstwą
   pakietów. Jądro, sterowniki, systemd, NetworkManager, PipeWire, KWin i Plasma pochodzą
   z oficjalnych, podpisanych repozytoriów Ubuntu i dostają aktualizacje bezpieczeństwa do 2029 r.
2. **Wszystko, co własne, jest pakietem `.deb`.** Dzięki temu NovaOS da się aktualizować
   (`apt`), a zmiany użytkownika w `/etc` są zachowywane (`conffiles`).
3. **Brak niepotrzebnych procesów.** Brak snapd (zablokowany przez APT pinning), apport,
   whoopsie, popularity-contest, Discover, telemetrii. Zram zamiast partycji wymiany.
4. **Bezpieczeństwo danych.** Instalator nie zaznacza żadnej opcji partycjonowania domyślnie
   i zawsze pyta przed zapisem (`prompt-install: true`). Aplikacje usuwają pliki do kosza,
   a operacje nieodwracalne wymagają potwierdzenia z przyciskiem „Anuluj” jako domyślnym.

## Warstwy

```
┌───────────────────────────────────────────────────────────────┐
│ Aplikacje Nova (PySide6)       novaos-apps                     │
│   novakit: motyw · i18n PL/EN · procesy · widżety              │
│   nova-helper (pkexec + polkit) – jedyny uprzywilejowany kod   │
├───────────────────────────────────────────────────────────────┤
│ Wygląd i tożsamość             novaos-desktop                  │
│   motyw globalny Plasma, schematy kolorów, panel (layout.js),  │
│   Centrum sterowania (plasmoid), KWin, SDDM, Plymouth, GRUB,   │
│   os-release (dpkg-divert), polecenie nova, fastfetch          │
├───────────────────────────────────────────────────────────────┤
│ KDE Plasma 6.6 / KWin Wayland / SDDM / PipeWire / NM / BlueZ   │
├───────────────────────────────────────────────────────────────┤
│ Ubuntu 26.04 LTS: Linux 7.0, systemd, APT, Flatpak, shim+GRUB  │
└───────────────────────────────────────────────────────────────┘
  Sesja live: casper + novaos-installer (Calamares) – usuwane po instalacji
```

## Proces budowania (`scripts/build-iso.sh`)

| Etap | Co robi |
|---|---|
| `bootstrap` | `debootstrap` minimalnego Ubuntu (resolute, amd64) |
| `packages` | źródła APT (deb822), blokada snap, instalacja list z `config/packages/*.list`, usunięcie `remove.list` |
| `novaos` | `make-debs.sh` → instalacja `novaos-*.deb`; opcjonalnie kompilacja efektu KWin „zaokrąglone rogi” (źródła pobierane na hoście, narzędzia kompilacji zawsze usuwane) |
| `finalize` | locale pl_PL, strefa czasowa, klawiatura, `casper.conf` (użytkownik live `nova`), usługi, Plymouth, initramfs, czyszczenie (logi, machine-id, cache APT) |
| `squashfs` | `filesystem.squashfs` (zstd‑19), manifest, kernel/initrd, `.disk/info` |
| `iso` | GRUB BIOS (El Torito, `grub-mkstandalone`), UEFI: podpisany `shimx64` + `gcdx64` (Secure Boot), partycja EFI dołączona jako GPT, `md5sum.txt`, hybrydowe ISO (`xorriso`), SHA‑256 |

Każdy etap zapisuje znacznik w `work/.stamps/`; przerwane budowanie wznawia się od miejsca
przerwania. `--from ETAP` przebudowuje od wskazanego etapu (np. po zmianie aplikacji wystarczy
`--from novaos`, co trwa kilka minut).

## Tożsamość systemu

`novaos-desktop` przejmuje przez `dpkg-divert` pliki `/usr/lib/os-release`, `/etc/lsb-release`,
`/etc/issue*` od `base-files`. `ID=novaos`, `ID_LIKE="ubuntu debian"`,
`VERSION_CODENAME`/`UBUNTU_CODENAME=resolute` – dzięki temu PPA, skrypty instalacyjne firm
trzecich (Docker, NVIDIA itd.) rozpoznają system jako zgodny z Ubuntu.

## Wygląd

- **Motyw globalny `org.novaos.desktop`** (Plasma Look-and-Feel): domyślne ustawienia,
  układ panelu (`layouts/org.kde.plasma.desktop-layout.js`) i ekran ładowania (`splash/Splash.qml`).
  Ustawiony w `/etc/xdg/kdeglobals`, więc stosuje się do każdego nowego konta.
- **Panel:** Kickoff (menu Start z ikoną `novaos-start`), przypięte aplikacje, zasobnik,
  `org.novaos.controlcenter`, zegar z kalendarzem, „pokaż pulpit”. Pływający, dopasowany do treści.
- **KWin (`/etc/xdg/kwinrc`):** blur, contrast, translucency, scale (animacja otwierania/zamykania),
  sliding popups, magic lamp, shake cursor; efekt `kwin4_effect_shapecorners` z gradientowym obrysem.
- **Kolory:** `NovaDark.colors` / `NovaLight.colors`, akcent `#7B61FF`, ikony Papirus(-Dark), font Inter.
- **SDDM:** własny motyw QML (Qt 6): zegar, awatary użytkowników, rozmyte tło, przyciski zasilania,
  obsługa błędnego hasła i Caps Lock. Ekran powitalny działa na Waylandzie (KWin).
- **Plymouth:** motyw `script` z pulsującym logo, paskiem postępu i polem hasła LUKS.

## Uprawnienia

Aplikacje działają jako zwykły użytkownik. Operacje administracyjne:
- przez usługi systemd z polkit (`timedatectl`, `localectl`, `hostnamectl`, `nmcli`, `flatpak`),
- albo przez **`/usr/libexec/novaos/nova-helper`** uruchamiany `pkexec` (akcja polkit
  `org.novaos.helper`, `auth_admin_keep`). Pomocnik ma zamkniętą listę poleceń
  (`apt-install`, `user-add`, `firewall`…), waliduje nazwy pakietów/użytkowników wyrażeniami
  regularnymi, czyta hasła wyłącznie ze stdin i odmawia usunięcia pakietów rdzenia systemu.

## Instalator

Calamares 3.3: powitanie (wymagania: 20 GB, 2 GB RAM) → lokalizacja → klawiatura → partycje
(GPT/EFI, ext4/btrfs/xfs, LUKS2) → użytkownik → podsumowanie → instalacja (rozpakowanie
squashfs, fstab, użytkownicy, SDDM, sieć, usunięcie pakietów live, initramfs, GRUB z shim
dla Secure Boot) → koniec. Identyfikator EFI to `ubuntu`, bo podpisany GRUB Canonical szuka
konfiguracji w `EFI/ubuntu/`; w menu rozruchu system nazywa się „NovaOS” (`GRUB_DISTRIBUTOR`).
