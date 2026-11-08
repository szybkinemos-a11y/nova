#!/usr/bin/env bash
# Nagrywa NovaOS.iso na pendrive.  UWAGA: kasuje WSZYSTKO na wskazanym urządzeniu.
#   sudo ./scripts/write-usb.sh /dev/sdX
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=../build.conf
source build.conf
DEV=${1:-}
ISO="$OUT_DIR/$ISO_NAME"
[[ $EUID -eq 0 ]] || { echo "Uruchom jako root"; exit 1; }
[[ -b $DEV ]] || { echo "Użycie: $0 /dev/sdX   (lista: lsblk -d -o NAME,SIZE,MODEL,TRAN)"; exit 1; }
[[ $(lsblk -dno TRAN "$DEV") == usb ]] || { echo "$DEV nie jest urządzeniem USB – przerywam dla bezpieczeństwa"; exit 1; }
if lsblk -no MOUNTPOINT "$DEV" | grep -q '^/$\|/boot'; then echo "$DEV zawiera bieżący system!"; exit 1; fi
lsblk -o NAME,SIZE,MODEL,MOUNTPOINT "$DEV"
read -r -p "Wszystkie dane na $DEV zostaną usunięte. Wpisz TAK, aby kontynuować: " ans
[[ $ans == TAK ]] || { echo "Anulowano."; exit 1; }
umount "$DEV"?* 2>/dev/null || true
dd if="$ISO" of="$DEV" bs=4M status=progress oflag=direct conv=fsync
sync
echo "Gotowe. Możesz uruchomić komputer z pendrive'a."
