#!/usr/bin/env bash
# Wspólne funkcje dla skryptów budowania NovaOS.
# shellcheck disable=SC2034

set -Eeuo pipefail

C_RESET=$'\e[0m'; C_VIO=$'\e[38;5;141m'; C_BLUE=$'\e[38;5;75m'
C_RED=$'\e[31m'; C_YEL=$'\e[33m'; C_GRN=$'\e[32m'

log()   { printf '%s[NovaOS]%s %s\n' "$C_VIO" "$C_RESET" "$*"; }
step()  { printf '\n%s==>%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_VIO" "$*" "$C_RESET"; }
ok()    { printf '%s  ✔%s %s\n' "$C_GRN" "$C_RESET" "$*"; }
warn()  { printf '%s  ! %s%s\n' "$C_YEL" "$*" "$C_RESET" >&2; }
die()   { printf '%s  ✘ %s%s\n' "$C_RED" "$*" "$C_RESET" >&2; exit 1; }

require_root() {
    [[ $EUID -eq 0 ]] || die "Ten skrypt wymaga uprawnień root (uruchom: sudo -E $0)"
}

require_cmds() {
    local missing=()
    for c in "$@"; do command -v "$c" >/dev/null 2>&1 || missing+=("$c"); done
    if ((${#missing[@]})); then
        die "Brak narzędzi: ${missing[*]}. Uruchom scripts/install-host-deps.sh albo zbuduj w Dockerze (scripts/docker-build.sh)."
    fi
}

# Czyta listę pakietów: pomija komentarze (#) i puste linie.
read_list() {
    local f
    for f in "$@"; do
        [[ -f $f ]] || die "Brak listy pakietów: $f"
        sed -e 's/#.*//' -e 's/[[:space:]]\+$//' "$f" | awk 'NF'
    done
}

# --- Stamps: pozwalają wznowić budowanie od przerwanego etapu ---------
stamp_done() { [[ -f "$STAMP_DIR/$1.done" ]]; }
stamp_set()  { mkdir -p "$STAMP_DIR"; date -Is > "$STAMP_DIR/$1.done"; }
stamp_clear_from() {
    # usuwa stamp podanego etapu i wszystkich kolejnych
    local found=0 s
    for s in "${ALL_STAGES[@]}"; do
        [[ $s == "$1" ]] && found=1
        ((found)) && rm -f "$STAMP_DIR/$s.done"
    done
}

# --- Montowanie systemów plików dla chroot ----------------------------
chroot_mount() {
    local d=$CHROOT_DIR
    mountpoint -q "$d/dev"     || mount --bind /dev "$d/dev"
    mountpoint -q "$d/dev/pts" || mount --bind /dev/pts "$d/dev/pts"
    mountpoint -q "$d/proc"    || mount -t proc proc "$d/proc"
    mountpoint -q "$d/sys"     || mount -t sysfs sysfs "$d/sys"
    mountpoint -q "$d/run"     || mount -t tmpfs tmpfs "$d/run"
    # DNS wewnątrz chroot
    rm -f "$d/etc/resolv.conf"
    cp -L /etc/resolv.conf "$d/etc/resolv.conf"
    # opcje APT/dpkg na czas budowania (bez pytań o pliki konfiguracyjne);
    # usuwane w etapie finalize
    if [[ -d $d/etc/apt/apt.conf.d ]]; then
        install -m644 "$PROJECT_DIR/config/apt/99novaos-build" "$d/etc/apt/apt.conf.d/99novaos-build"
    fi
}

chroot_umount() {
    local d=${CHROOT_DIR:-}
    [[ -n $d && -d $d ]] || return 0
    local m
    for m in run sys proc dev/pts dev; do
        if mountpoint -q "$d/$m" 2>/dev/null; then
            umount -lf "$d/$m" 2>/dev/null || warn "Nie udało się odmontować $d/$m"
        fi
    done
}

# Uruchamia polecenie w chroot z czystym środowiskiem.
in_chroot() {
    chroot "$CHROOT_DIR" /usr/bin/env -i \
        HOME=/root TERM="${TERM:-xterm}" LANG=C.UTF-8 \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin \
        DEBIAN_FRONTEND=noninteractive DEBCONF_NONINTERACTIVE_SEEN=true \
        "$@"
}

# Blokuje uruchamianie usług podczas instalacji pakietów w chroot.
policy_rc_block()   { printf '#!/bin/sh\nexit 101\n' > "$CHROOT_DIR/usr/sbin/policy-rc.d"; chmod +x "$CHROOT_DIR/usr/sbin/policy-rc.d"; }
policy_rc_unblock() { rm -f "$CHROOT_DIR/usr/sbin/policy-rc.d"; }

# Podstawia zmienne @NAZWA@ w plikach szablonów.
render_template() {
    local src=$1 dst=$2
    sed -e "s|@DISTRO_NAME@|$DISTRO_NAME|g" \
        -e "s|@DISTRO_ID@|$DISTRO_ID|g" \
        -e "s|@DISTRO_VERSION@|$DISTRO_VERSION|g" \
        -e "s|@DISTRO_CODENAME@|$DISTRO_CODENAME|g" \
        -e "s|@DISTRO_PRETTY@|$DISTRO_PRETTY|g" \
        -e "s|@DISTRO_URL@|$DISTRO_URL|g" \
        -e "s|@UBUNTU_CODENAME@|$UBUNTU_CODENAME|g" \
        -e "s|@UBUNTU_VERSION@|$UBUNTU_VERSION|g" \
        -e "s|@ISO_LABEL@|$ISO_LABEL|g" \
        -e "s|@LIVE_USER@|$LIVE_USER|g" \
        -e "s|@LIVE_HOSTNAME@|$LIVE_HOSTNAME|g" \
        -e "s|@DEFAULT_LOCALE@|$DEFAULT_LOCALE|g" \
        -e "s|@DEFAULT_TIMEZONE@|$DEFAULT_TIMEZONE|g" \
        -e "s|@DEFAULT_KEYMAP@|$DEFAULT_KEYMAP|g" \
        "$src" > "$dst"
}
