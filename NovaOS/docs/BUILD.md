# Budowanie i uruchamianie NovaOS

## Wymagania hosta

- Linux x86_64, uprawnienia root, ~25 GB wolnego miejsca, połączenie z internetem
  (pobieranie ok. 2,5 GB pakietów z archive.ubuntu.com).
- Czas: 20–40 min (zależnie od łącza i CPU). Przebudowa po zmianie aplikacji: kilka minut.

### Opcja A – kontener (zalecana na Arch Linux, Fedorze itd.)

```bash
# Arch:   sudo pacman -S podman     (albo docker)
sudo ./scripts/docker-build.sh
```
Kontener `ubuntu:26.04` ma wszystkie narzędzia; potrzebuje `--privileged` (montowanie
`/proc` i `/dev` w chroot). Wynik pojawi się w `out/`.

### Opcja B – bezpośrednio na Ubuntu/Debianie

```bash
sudo ./scripts/install-host-deps.sh
sudo ./scripts/build-iso.sh
```

### Przydatne opcje

```bash
sudo ./scripts/build-iso.sh --from novaos     # przebuduj od etapu (bootstrap|packages|novaos|finalize|squashfs|iso)
sudo ./scripts/build-iso.sh --only iso        # tylko jeden etap
sudo ./scripts/build-iso.sh --clean           # od zera
sudo MIRROR=http://pl.archive.ubuntu.com/ubuntu ./scripts/build-iso.sh   # polski mirror
sudo ENABLE_ROUNDED_CORNERS=no ./scripts/build-iso.sh                   # bez kompilacji efektu
sudo SQUASHFS_COMP=xz ./scripts/build-iso.sh                            # mniejsze ISO, wolniejszy live
```
Wszystkie ustawienia są w `build.conf` (nazwa, wersja, język, strefa czasowa, użytkownik live…).

## Uruchomienie

### QEMU
```bash
./scripts/test-qemu.sh            # UEFI
./scripts/test-qemu.sh --bios     # BIOS
./scripts/test-qemu.sh --install  # z dyskiem 32 GB (test instalacji)
./scripts/test-qemu.sh --disk     # start zainstalowanego systemu z dysku
```

### VirtualBox (7.x)
1. Nowa maszyna → typ Linux, wersja **Ubuntu (64-bit)**.
2. RAM 4096 MB, CPU 2–4, dysk VDI 30 GB.
3. Ustawienia → System → **Włącz EFI**. Ekran → VMSVGA, 128 MB, **akceleracja 3D**.
4. Pamięć → napęd optyczny → `NovaOS.iso`. Start.

### VMware Workstation / Player
1. „Typical” → „I will install the operating system later” → Linux / **Ubuntu 64-bit**.
2. 4 GB RAM, 2+ CPU, dysk 30 GB.
3. Customize Hardware → CD/DVD → `NovaOS.iso`; Display → **Accelerate 3D graphics**.
4. Options → Advanced → Firmware type **UEFI** (opcjonalnie Secure Boot – działa, bo shim i GRUB są podpisane).

### Pendrive
```bash
lsblk -d -o NAME,SIZE,MODEL,TRAN            # znajdź pendrive (np. sdb)
sudo ./scripts/write-usb.sh /dev/sdb         # pyta o potwierdzenie „TAK”
```
Na Windowsie: Rufus (tryb „DD”) albo balenaEtcher. Obraz jest hybrydowy: działa jako DVD
i jako dysk USB, w trybie UEFI i BIOS.

### Prawdziwy komputer
1. Uruchom z pendrive'a (menu rozruchu: F12/F11/F8/Esc zależnie od producenta).
2. Secure Boot może zostać włączony.
3. W menu GRUB wybierz „Uruchom NovaOS”. Po starcie pojawi się okno „Wypróbuj / Zainstaluj”.

## Instalacja na dysk

Instalator (ikona na pulpicie lub `novaos-install`):
1. Język → strefa czasowa (domyślnie Europa/Warszawa) → klawiatura (polski).
2. Partycje: **nic nie jest zaznaczone domyślnie**. Do wyboru: wymaż dysk (opcjonalnie
   z szyfrowaniem LUKS2), zainstaluj obok innego systemu, zastąp partycję, ręcznie.
   UEFI → GPT + partycja EFI 512 MB; BIOS → MBR/GPT.
3. Użytkownik i hasło (administrator, grupa `sudo`).
4. Podsumowanie → **Zainstaluj** → potwierdzenie → postęp → restart.

Po instalacji: Flathub zostanie skonfigurowany przy pierwszym połączeniu z internetem
(`novaos-flathub.service`), zapora `ufw` jest włączona, zram aktywny.

## Rozwiązywanie problemów

| Objaw | Rozwiązanie |
|---|---|
| Czarny ekran w VirtualBox | włącz EFI i VMSVGA + 3D; albo wybierz w GRUB „tryb bezpieczny grafiki” |
| `debootstrap: Release signature` | zainstaluj `ubuntu-keyring` (Arch: AUR) lub użyj `docker-build.sh` |
| Brak zaokrąglonych rogów | efekt kompiluje się ze źródeł GitHub; sprawdź log etapu `novaos` lub ustaw `ENABLE_ROUNDED_CORNERS=no` |
| Instalator: log | `~/.cache/novaos-install.log` oraz `/root/.cache/calamares/session.log` |
