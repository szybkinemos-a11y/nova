#!/usr/bin/env bash
# Etap 5: skompresowany system plików (casper/filesystem.squashfs)

CRITICAL_PACKAGES=(linux-generic casper plasma-desktop plasma-workspace kwin-wayland sddm
                   network-manager pipewire novaos-desktop novaos-apps novaos-installer calamares
                   shim-signed grub-efi-amd64-signed)

verify_chroot() {
    local p missing=()
    for p in "${CRITICAL_PACKAGES[@]}"; do
        chroot "$CHROOT_DIR" dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || missing+=("$p")
    done
    ((${#missing[@]} == 0)) || die "Brak krytycznych pakietów w systemie: ${missing[*]}"
    [[ -e $CHROOT_DIR/boot/vmlinuz && -e $CHROOT_DIR/boot/initrd.img ]] || die "Brak jądra/initrd w /boot"
    ok "Kontrola systemu: wszystkie krytyczne pakiety obecne"
}

stage_squashfs() {
    chroot_umount
    verify_chroot
    rm -rf "$IMAGE_DIR"
    mkdir -p "$IMAGE_DIR"/{casper,boot/grub,EFI/boot,.disk}

    log "Manifest pakietów"
    chroot "$CHROOT_DIR" dpkg-query -W --showformat='${Package} ${Version}\n' > "$IMAGE_DIR/casper/filesystem.manifest"
    # pakiety usuwane przez instalator z docelowego systemu
    printf '%s\n' calamares casper novaos-installer > "$IMAGE_DIR/casper/filesystem.manifest-remove"

    log "Jądro i initrd"
    cp -L "$CHROOT_DIR/boot/vmlinuz" "$IMAGE_DIR/casper/vmlinuz"
    cp -L "$CHROOT_DIR/boot/initrd.img" "$IMAGE_DIR/casper/initrd"

    log "mksquashfs ($SQUASHFS_COMP) – to potrwa kilka minut"
    local comp=(-comp "$SQUASHFS_COMP")
    [[ $SQUASHFS_COMP == zstd ]] && comp+=(-Xcompression-level 6)
    [[ $SQUASHFS_COMP == xz ]] && comp+=(-Xbcj x86)
    mksquashfs "$CHROOT_DIR" "$IMAGE_DIR/casper/filesystem.squashfs" \
        -noappend -b 1M "${comp[@]}" -no-progress \
        -wildcards -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'tmp/*' 'var/tmp/*' 'var/cache/apt/archives/*.deb'
    du -sx --block-size=1 "$CHROOT_DIR" | cut -f1 > "$IMAGE_DIR/casper/filesystem.size"
    ok "filesystem.squashfs: $(du -h "$IMAGE_DIR/casper/filesystem.squashfs" | cut -f1)"

    echo "$DISTRO_NAME $DISTRO_VERSION \"${DISTRO_CODENAME^}\" - Release $ARCH ($(date +%Y%m%d))" > "$IMAGE_DIR/.disk/info"
    echo "full_cd/single" > "$IMAGE_DIR/.disk/cd_type"
    touch "$IMAGE_DIR/.disk/base_installable"
    echo "$DISTRO_URL" > "$IMAGE_DIR/.disk/release_notes_url"
}
