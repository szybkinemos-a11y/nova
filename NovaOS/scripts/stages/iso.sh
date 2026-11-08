#!/usr/bin/env bash
# Etap 6: rozruch (GRUB BIOS + UEFI/Secure Boot) i obraz NovaOS.iso (hybrydowy: DVD + USB)

stage_iso() {
    local G="$IMAGE_DIR/boot/grub" T="$WORK_DIR/iso-tmp"
    rm -rf "$T"
    mkdir -p "$G/fonts" "$G/themes" "$T"
    chroot_mount

    log "Konfiguracja GRUB + motyw NovaOS"
    render_template "$PROJECT_DIR/config/grub/grub.cfg" "$G/grub.cfg"
    cp "$CHROOT_DIR/usr/share/grub/unicode.pf2" "$G/fonts/"
    cp -r "$CHROOT_DIR/usr/share/grub/themes/novaos" "$G/themes/"
    local spec style size
    for spec in "Regular 14" "Regular 16" "Regular 18" "Bold 18" "Bold 32"; do
        read -r style size <<< "$spec"
        in_chroot grub-mkfont -s "$size" -o "/tmp/inter-${style,,}-$size.pf2" "/usr/share/fonts/opentype/inter/Inter-$style.otf"
        mv "$CHROOT_DIR/tmp/inter-${style,,}-$size.pf2" "$G/themes/novaos/"
    done

    # Konfiguracja wbudowana w obrazy GRUB: znajdź nośnik i wczytaj właściwy grub.cfg
    cat > "$CHROOT_DIR/tmp/embed.cfg" <<'EMBED'
search --no-floppy --set=root --file /.disk/info
set prefix=($root)/boot/grub
configfile ($root)/boot/grub/grub.cfg
EMBED
    local mods="linux linux16 normal iso9660 biosdisk memdisk search search_fs_file tar ls all_video gfxterm gfxmenu png font configfile echo test true reboot halt part_gpt part_msdos fat"

    log "Rozruch BIOS (El Torito)"
    in_chroot grub-mkstandalone --format=i386-pc --output=/tmp/core.img \
        --install-modules="$mods" --modules="linux normal iso9660 biosdisk search" \
        --locales="" --fonts="" "boot/grub/grub.cfg=/tmp/embed.cfg"
    cat "$CHROOT_DIR/usr/lib/grub/i386-pc/cdboot.img" "$CHROOT_DIR/tmp/core.img" > "$G/bios.img"

    log "Rozruch UEFI"
    local shim="" grubefi="" mm=""
    for f in /usr/lib/shim/shimx64.efi.signed.latest /usr/lib/shim/shimx64.efi.signed; do
        [[ -f $CHROOT_DIR$f ]] && { shim=$CHROOT_DIR$f; break; }
    done
    [[ -f $CHROOT_DIR/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed ]] && grubefi=$CHROOT_DIR/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed
    [[ -f $CHROOT_DIR/usr/lib/shim/mmx64.efi ]] && mm=$CHROOT_DIR/usr/lib/shim/mmx64.efi
    if [[ -n $shim && -n $grubefi ]]; then
        ok "Secure Boot: podpisany shim + GRUB (Canonical)"
        cp "$shim" "$IMAGE_DIR/EFI/boot/bootx64.efi"
        cp "$grubefi" "$IMAGE_DIR/EFI/boot/grubx64.efi"
        [[ -n $mm ]] && cp "$mm" "$IMAGE_DIR/EFI/boot/mmx64.efi"
    else
        warn "Brak podpisanych plików EFI – GRUB bez Secure Boot"
        in_chroot grub-mkstandalone --format=x86_64-efi --output=/tmp/bootx64.efi \
            --install-modules="$mods" --locales="" --fonts="" "boot/grub/grub.cfg=/tmp/embed.cfg"
        cp "$CHROOT_DIR/tmp/bootx64.efi" "$IMAGE_DIR/EFI/boot/bootx64.efi"
    fi
    # Partycja systemowa EFI (FAT) dołączana do obrazu
    local efi_img="$T/efi.img" size_kb
    size_kb=$(( $(du -sk "$IMAGE_DIR/EFI" | cut -f1) + 2048 ))
    dd if=/dev/zero of="$efi_img" bs=1K count="$size_kb" status=none
    mkfs.vfat -n NOVAOS_EFI "$efi_img" >/dev/null
    mmd -i "$efi_img" ::/EFI ::/EFI/boot
    mcopy -i "$efi_img" "$IMAGE_DIR"/EFI/boot/* ::/EFI/boot/
    rm -f "$CHROOT_DIR"/tmp/{embed.cfg,core.img,bootx64.efi}
    cp "$CHROOT_DIR/usr/lib/grub/i386-pc/boot_hybrid.img" "$T/boot_hybrid.img"
    chroot_umount

    log "Sumy kontrolne nośnika (dla 'Sprawdź nośnik')"
    (cd "$IMAGE_DIR" && find . -type f ! -name md5sum.txt ! -name bios.img -print0 | sort -z | xargs -0 md5sum > "$T/md5sum.txt")
    mv "$T/md5sum.txt" "$IMAGE_DIR/md5sum.txt"

    log "Tworzenie $ISO_NAME (xorriso)"
    local iso="$OUT_DIR/$ISO_NAME"
    rm -f "$iso"
    xorriso -as mkisofs -r -V "$ISO_LABEL" -o "$iso" \
        -J -joliet-long -l -iso-level 3 \
        -partition_offset 16 \
        --grub2-mbr "$T/boot_hybrid.img" --mbr-force-bootable \
        -append_partition 2 0xEF "$efi_img" -appended_part_as_gpt \
        -c /boot.catalog \
        -b /boot/grub/bios.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
        -eltorito-alt-boot -e '--interval:appended_partition_2:all::' -no-emul-boot \
        "$IMAGE_DIR" 2>&1 | grep -vE '^(xorriso|libisofs|Drive current|Media current|Media status|Media summary|Added to ISO|Writing to|Production|Rock Ridge|Sorting|UPDATE)' || true
    [[ -s $iso ]] || die "Nie utworzono $iso"
    (cd "$OUT_DIR" && sha256sum "$ISO_NAME" > "$ISO_NAME.sha256")
    ok "$iso ($(du -h "$iso" | cut -f1))"
    rm -rf "$T"
}
