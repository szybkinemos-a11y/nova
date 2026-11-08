#!/usr/bin/env bash
# Etap 2: źródła APT i instalacja pakietów z config/packages/*.list

stage_packages() {
    chroot_mount
    policy_rc_block

    log "Konfiguracja źródeł APT (format deb822)"
    rm -f "$CHROOT_DIR/etc/apt/sources.list"
    mkdir -p "$CHROOT_DIR/etc/apt/sources.list.d" "$CHROOT_DIR/etc/apt/preferences.d"
    cat > "$CHROOT_DIR/etc/apt/sources.list.d/ubuntu.sources" <<EOF
Types: deb
URIs: $MIRROR
Suites: $UBUNTU_CODENAME $UBUNTU_CODENAME-updates $UBUNTU_CODENAME-backports
Components: $COMPONENTS
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: $SECURITY_MIRROR
Suites: $UBUNTU_CODENAME-security
Components: $COMPONENTS
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
    # NovaOS nie używa snapów – blokujemy snapd (mniej procesów w tle)
    install -m644 "$PROJECT_DIR/config/apt/no-snap.pref" "$CHROOT_DIR/etc/apt/preferences.d/no-snap.pref"
    install -m644 "$PROJECT_DIR/config/apt/99novaos-build" "$CHROOT_DIR/etc/apt/apt.conf.d/99novaos-build"

    echo "$LIVE_HOSTNAME" > "$CHROOT_DIR/etc/hostname"
    in_chroot dbus-uuidgen --ensure=/etc/machine-id 2>/dev/null || true

    log "Aktualizacja systemu bazowego"
    in_chroot apt-get update
    in_chroot apt-get -y full-upgrade

    # Ustawienia debconf przed instalacją (klawiatura, locale, sddm)
    in_chroot debconf-set-selections <<EOF
keyboard-configuration keyboard-configuration/layoutcode string $DEFAULT_KEYMAP
keyboard-configuration keyboard-configuration/variant select Polish
locales locales/default_environment_locale select $DEFAULT_LOCALE
locales locales/locales_to_be_generated multiselect $DEFAULT_LOCALE UTF-8, ${EXTRA_LOCALES} UTF-8
sddm shared/default-x-display-manager select sddm
EOF

    local rec="--no-install-recommends"
    [[ $INSTALL_RECOMMENDS == yes ]] && rec="--install-recommends"

    local list
    for list in base desktop apps installer; do
        log "Instalacja pakietów: $list.list"
        # shellcheck disable=SC2046
        in_chroot apt-get install -y $rec $(read_list "$PROJECT_DIR/config/packages/$list.list")
    done

    log "Usuwanie zbędnych pakietów (config/packages/remove.list)"
    local remove=()
    mapfile -t remove < <(read_list "$PROJECT_DIR/config/packages/remove.list")
    local installed=()
    for p in "${remove[@]}"; do
        in_chroot dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" && installed+=("$p")
    done
    ((${#installed[@]})) && in_chroot apt-get purge -y "${installed[@]}"
    in_chroot apt-get autoremove -y --purge

    policy_rc_unblock
    chroot_umount
}
