#!/usr/bin/env bash
# =====================================================================
#  NovaOS – budowanie obrazu NovaOS.iso na bazie Ubuntu LTS
#
#  Użycie:
#     sudo ./scripts/build-iso.sh              # pełne budowanie (wznawia od przerwanego etapu)
#     sudo ./scripts/build-iso.sh --from novaos # przebuduj od wskazanego etapu
#     sudo ./scripts/build-iso.sh --only iso    # tylko jeden etap
#     sudo ./scripts/build-iso.sh --clean       # usuń katalog roboczy i zacznij od zera
#
#  Etapy: bootstrap → packages → novaos → finalize → squashfs → iso
# =====================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../build.conf
source "$SCRIPT_DIR/../build.conf"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

ALL_STAGES=(bootstrap packages novaos finalize squashfs iso)
FROM="" ONLY="" CLEAN=0

usage() { sed -n '3,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while (($#)); do
    case $1 in
        --from)  FROM=$2; shift ;;
        --only)  ONLY=$2; shift ;;
        --clean) CLEAN=1 ;;
        -h|--help) usage ;;
        *) die "Nieznana opcja: $1" ;;
    esac
    shift
done

require_root
# budowanie jest nienadzorowane: żadne polecenie nie może czekać na klawiaturę
exec </dev/null
require_cmds debootstrap mksquashfs xorriso grub-mkstandalone mkfs.vfat mcopy mmd rsync dpkg-deb

trap 'chroot_umount' EXIT
trap 'die "Budowanie przerwane w linii $LINENO (etap: ${CURRENT_STAGE:-?})"' ERR

if ((CLEAN)); then
    step "Czyszczenie $WORK_DIR"
    chroot_umount
    rm -rf "$WORK_DIR"
fi
mkdir -p "$WORK_DIR" "$OUT_DIR" "$STAMP_DIR"

[[ -n $FROM ]] && stamp_clear_from "$FROM"
[[ -n $ONLY ]] && rm -f "$STAMP_DIR/$ONLY.done"

START=$(date +%s)
for stage in "${ALL_STAGES[@]}"; do
    if [[ -n $ONLY && $stage != "$ONLY" ]]; then continue; fi
    if stamp_done "$stage"; then ok "Etap '$stage' już wykonany – pomijam"; continue; fi
    CURRENT_STAGE=$stage
    step "Etap: $stage"
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/stages/$stage.sh"
    "stage_$stage"
    stamp_set "$stage"
    ok "Etap '$stage' zakończony"
done

chroot_umount
ELAPSED=$(( $(date +%s) - START ))
step "Gotowe w $((ELAPSED/60)) min $((ELAPSED%60)) s"
if [[ -f "$OUT_DIR/$ISO_NAME" ]]; then
    log "Obraz: $OUT_DIR/$ISO_NAME ($(du -h "$OUT_DIR/$ISO_NAME" | cut -f1))"
fi
exit 0
