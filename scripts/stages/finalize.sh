#!/usr/bin/env bash
# Etap 4: konfiguracja systemu live, locale, usługi, czyszczenie

stage_finalize() {
    chroot_mount
    policy_rc_block

    log "Locale i strefa czasowa"
    in_chroot sh -c "sed -i -e 's/^# *\\(pl_PL.UTF-8\\)/\\1/' -e 's/^# *\\(en_US.UTF-8\\)/\\1/' /etc/locale.gen && locale-gen"
    in_chroot update-locale LANG="$DEFAULT_LOCALE" LANGUAGE="${DEFAULT_LOCALE%%.*}:pl" 
    ln -sf "/usr/share/zoneinfo/$DEFAULT_TIMEZONE" "$CHROOT_DIR/etc/localtime"
    echo "$DEFAULT_TIMEZONE" > "$CHROOT_DIR/etc/timezone"
    cat > "$CHROOT_DIR/etc/default/keyboard" <<KBD
XKBMODEL="pc105"
XKBLAYOUT="$DEFAULT_KEYMAP,us"
XKBVARIANT=","
XKBOPTIONS="grp:win_space_toggle"
BACKSPACE="guess"
KBD

    log "Sesja live (casper)"
    cat > "$CHROOT_DIR/etc/casper.conf" <<CASPER
# NovaOS – konfiguracja sesji live
export USERNAME="$LIVE_USER"
export USERFULLNAME="NovaOS Live"
export HOST="$LIVE_HOSTNAME"
export BUILD_SYSTEM="Ubuntu"
export FLAVOUR="NovaOS"
CASPER
    echo "$LIVE_HOSTNAME" > "$CHROOT_DIR/etc/hostname"
    printf '127.0.0.1\tlocalhost\n127.0.1.1\t%s\n::1\tlocalhost ip6-localhost ip6-loopback\n' "$LIVE_HOSTNAME" \
        > "$CHROOT_DIR/etc/hosts"

    log "Usługi systemowe"
    in_chroot systemctl enable NetworkManager.service sddm.service bluetooth.service \
        novaos-flathub.service ufw.service 2>/dev/null || true
    in_chroot systemctl set-default graphical.target
    # brak zbędnych usług w tle
    in_chroot systemctl disable apport.service whoopsie.service 2>/dev/null || true
    in_chroot systemctl mask systemd-networkd-wait-online.service >/dev/null 2>&1 || true

    log "Plymouth, initramfs"
    in_chroot update-alternatives --set default.plymouth /usr/share/plymouth/themes/novaos/novaos.plymouth || true
    in_chroot update-initramfs -c -k all 2>/dev/null || in_chroot update-initramfs -u -k all

    log "Czyszczenie obrazu"
    in_chroot apt-get clean
    rm -rf "$CHROOT_DIR"/var/lib/apt/lists/* "$CHROOT_DIR"/tmp/* "$CHROOT_DIR"/var/tmp/* \
           "$CHROOT_DIR"/root/.cache "$CHROOT_DIR"/root/.bash_history
    find "$CHROOT_DIR/var/log" -type f -exec truncate -s 0 {} +
    : > "$CHROOT_DIR/etc/machine-id"
    rm -f "$CHROOT_DIR/var/lib/dbus/machine-id"
    rm -f "$CHROOT_DIR/etc/resolv.conf"
    ln -s ../run/systemd/resolve/stub-resolv.conf "$CHROOT_DIR/etc/resolv.conf"

    policy_rc_unblock
    chroot_umount
    rm -f "$CHROOT_DIR/etc/apt/apt.conf.d/99novaos-build"
}
