#!/usr/bin/env bash
# Buduje NovaOS.iso w kontenerze (Docker lub Podman) – zalecane na Arch/Fedora.
#   sudo ./scripts/docker-build.sh            # pełne budowanie
#   sudo ./scripts/docker-build.sh --clean    # od zera
# Kontener potrzebuje --privileged (montowanie /proc, /dev w chroot).
set -euo pipefail
cd "$(dirname "$0")/.."
ENGINE=${ENGINE:-$(command -v podman || command -v docker || true)}
[[ -n $ENGINE ]] || { echo "Zainstaluj Docker albo Podman (Arch: pacman -S podman)"; exit 1; }
IMAGE=novaos-builder:26.04
"$ENGINE" build -t "$IMAGE" .
exec "$ENGINE" run --rm --privileged \
    -v "$PWD":/novaos \
    -e MIRROR="${MIRROR:-http://archive.ubuntu.com/ubuntu}" \
    -e ENABLE_ROUNDED_CORNERS="${ENABLE_ROUNDED_CORNERS:-yes}" \
    "$IMAGE" "$@"
