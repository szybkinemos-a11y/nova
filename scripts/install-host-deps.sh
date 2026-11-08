#!/usr/bin/env bash
# Instaluje narzędzia potrzebne do zbudowania NovaOS.iso na komputerze-hoście.
# Obsługiwane: Ubuntu/Debian, Arch Linux (i pochodne), Fedora.
# Najprostsza i najbardziej powtarzalna droga to jednak Docker/Podman:
#     sudo ./scripts/docker-build.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "Uruchom jako root: sudo $0"; exit 1; fi

. /etc/os-release
case " ${ID} ${ID_LIKE:-} " in
    *" ubuntu "*|*" debian "*)
        apt-get update
        apt-get install -y debootstrap squashfs-tools xorriso grub-pc-bin \
            grub-efi-amd64-bin grub-common mtools dosfstools rsync librsvg2-bin \
            fonts-inter python3 qemu-system-x86 ovmf shellcheck
        ;;
    *" arch "*)
        # debootstrap + klucze Ubuntu (ubuntu-keyring z AUR lub z extra)
        pacman -Syu --needed --noconfirm debootstrap squashfs-tools libisoburn \
            grub mtools dosfstools rsync librsvg inter-font python qemu-desktop \
            edk2-ovmf shellcheck dpkg
        if ! [[ -f /usr/share/keyrings/ubuntu-archive-keyring.gpg ]]; then
            echo ">> Brak klucza archiwum Ubuntu. Zainstaluj 'ubuntu-keyring' (AUR):"
            echo "     yay -S ubuntu-keyring"
            echo "   albo użyj budowania w Dockerze: sudo ./scripts/docker-build.sh"
        fi
        ;;
    *" fedora "*)
        dnf install -y debootstrap squashfs-tools xorriso grub2-tools-extra \
            grub2-pc-modules grub2-efi-x64-modules mtools dosfstools rsync \
            librsvg2-tools rsms-inter-fonts python3 qemu-system-x86 edk2-ovmf \
            ShellCheck dpkg
        ;;
    *)
        echo "Nieobsługiwana dystrybucja ($ID). Użyj: sudo ./scripts/docker-build.sh"
        exit 1
        ;;
esac
echo "Gotowe. Teraz: sudo ./scripts/build-iso.sh"
