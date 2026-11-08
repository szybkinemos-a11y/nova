#!/usr/bin/env bash
# Etap 1: minimalny system Ubuntu przez debootstrap.

stage_bootstrap() {
    chroot_umount
    rm -rf "$CHROOT_DIR"
    mkdir -p "$CHROOT_DIR"

    # Starsze wersje debootstrap nie znają nowych wydań Ubuntu –
    # wszystkie wydania Ubuntu używają wtedy wspólnego skryptu "gutsy".
    local script="/usr/share/debootstrap/scripts/$UBUNTU_CODENAME"
    [[ -e $script ]] || script="/usr/share/debootstrap/scripts/gutsy"

    log "debootstrap $UBUNTU_CODENAME ($ARCH) z $MIRROR"
    debootstrap --arch="$ARCH" --variant=minbase \
        --components="${COMPONENTS// /,}" \
        --include=ca-certificates,gnupg,apt-utils \
        "$UBUNTU_CODENAME" "$CHROOT_DIR" "$MIRROR" "$script"
}
