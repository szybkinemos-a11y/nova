#!/usr/bin/env bash
# =====================================================================
#  Test NovaOS.iso w maszynie wirtualnej QEMU
#    ./scripts/test-qemu.sh                 # UEFI, okno graficzne
#    ./scripts/test-qemu.sh --bios          # tryb BIOS (legacy)
#    ./scripts/test-qemu.sh --install       # z dyskiem 32 GB do testu instalacji
#    ./scripts/test-qemu.sh --disk          # uruchom zainstalowany system z dysku
#    ./scripts/test-qemu.sh --headless 240  # bez okna; zrzuty ekranu co 30 s (do out/qemu-*.png)
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=../build.conf
source build.conf
ISO="$OUT_DIR/$ISO_NAME"
DISK="$OUT_DIR/novaos-test.qcow2"
MODE=uefi INSTALL=0 BOOT_DISK=0 HEADLESS=0 SECONDS_RUN=0
while (($#)); do
    case $1 in
        --bios) MODE=bios ;;
        --install) INSTALL=1 ;;
        --disk) BOOT_DISK=1; INSTALL=1 ;;
        --headless) HEADLESS=1; SECONDS_RUN=${2:-240}; shift ;;
        *) echo "Nieznana opcja: $1"; exit 1 ;;
    esac
    shift
done
[[ -f $ISO || $BOOT_DISK -eq 1 ]] || { echo "Brak $ISO – najpierw zbuduj obraz"; exit 1; }

ARGS=(-m 4096 -smp "$(nproc)" -device "virtio-net-pci,netdev=n0" -netdev "user,id=n0"
      -device intel-hda -device hda-duplex -usb -device usb-tablet -vga virtio)
if [[ -e /dev/kvm && -w /dev/kvm ]]; then ARGS+=(-enable-kvm -cpu host); else
    echo "! Brak KVM – emulacja programowa będzie bardzo wolna"; ARGS+=(-cpu max); fi
if [[ $MODE == uefi ]]; then
    for f in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd /usr/share/edk2/x64/OVMF_CODE.4m.fd \
             /usr/share/edk2-ovmf/x64/OVMF_CODE.fd /usr/share/qemu/OVMF.fd; do
        [[ -f $f ]] && { OVMF=$f; break; }
    done
    [[ -n ${OVMF:-} ]] || { echo "Brak OVMF (pakiet ovmf / edk2-ovmf)"; exit 1; }
    VARS="$OUT_DIR/OVMF_VARS.fd"
    [[ -f $VARS ]] || cp "$(dirname "$OVMF")/$(basename "$OVMF" | sed 's/CODE/VARS/')" "$VARS" 2>/dev/null \
        || truncate -s "$(stat -c %s "$OVMF")" "$VARS"
    ARGS+=(-machine q35 -drive "if=pflash,format=raw,readonly=on,file=$OVMF" -drive "if=pflash,format=raw,file=$VARS")
fi
if ((INSTALL)); then
    [[ -f $DISK ]] || qemu-img create -f qcow2 "$DISK" 32G
    ARGS+=(-drive "file=$DISK,if=virtio,format=qcow2")
fi
((BOOT_DISK)) || ARGS+=(-cdrom "$ISO" -boot d)

if ((HEADLESS)); then
    MON="$OUT_DIR/qemu-monitor.sock"
    rm -f "$MON"
    qemu-system-x86_64 "${ARGS[@]}" -display none -monitor "unix:$MON,server,nowait" -serial "file:$OUT_DIR/qemu-serial.log" &
    PID=$!
    for ((t = 30; t <= SECONDS_RUN; t += 30)); do
        sleep 30
        kill -0 $PID 2>/dev/null || break
        echo "screendump $OUT_DIR/qemu-${t}s.ppm" | socat - "UNIX-CONNECT:$MON" >/dev/null 2>&1 \
            || python3 -c "import socket,sys;s=socket.socket(socket.AF_UNIX);s.connect('$MON');s.sendall(b'screendump $OUT_DIR/qemu-${t}s.ppm\n');import time;time.sleep(1)"
        echo "zrzut po ${t}s: $OUT_DIR/qemu-${t}s.ppm"
    done
    kill $PID 2>/dev/null || true
else
    exec qemu-system-x86_64 "${ARGS[@]}"
fi
