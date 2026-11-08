#!/usr/bin/env bash
# Etap 3: pakiety NovaOS (.deb) + zaokrąglone rogi okien (opcjonalnie)

purge_unwanted() {
    local remove=() installed=() p
    mapfile -t remove < <(read_list "$PROJECT_DIR/config/packages/remove.list")
    for p in "${remove[@]}"; do
        if in_chroot dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed"; then
            installed+=("$p")
        fi
    done
    if ((${#installed[@]})); then
        log "Usuwanie: ${installed[*]}"
        in_chroot apt-get purge -y "${installed[@]}"
    fi
    in_chroot apt-get autoremove -y --purge
}

fetch_rounded_corners_src() {
    # Źródła pobieramy na hoście (git + certyfikaty hosta), budujemy w chroot.
    local src="$WORK_DIR/src/KDE-Rounded-Corners"
    command -v git >/dev/null || { warn "Brak git na hoście"; return 1; }
    if [[ -d $src/.git ]]; then
        if git -C "$src" fetch --depth 1 origin "$ROUNDED_CORNERS_REF" >/dev/null 2>&1; then
            git -C "$src" checkout -q FETCH_HEAD
        fi
    else
        rm -rf "$src"
        git clone -q --depth 1 --branch "$ROUNDED_CORNERS_REF" "$ROUNDED_CORNERS_REPO" "$src" || return 1
    fi
    log "KDE-Rounded-Corners: $(git -C "$src" log -1 --format='%h %cs')"
    rm -rf "$CHROOT_DIR/tmp/krc"
    cp -a "$src" "$CHROOT_DIR/tmp/krc"
}

build_rounded_corners() {
    local deps=(build-essential cmake gettext extra-cmake-modules qt6-base-private-dev qt6-base-dev-tools
                libkf6configwidgets-dev libkf6kcmutils-dev kwin-dev libdrm-dev)
    log "Budowanie efektu KWin: zaokrąglone rogi okien"
    fetch_rounded_corners_src || return 1
    # Zapamiętaj stan przed instalacją narzędzi. Po kompilacji usuwamy WYŁĄCZNIE
    # pakiety doinstalowane teraz (apt-mark auto + autoremove), bo część "narzędzi"
    # jest zależnością pulpitu (np. plasma-workspace -> qt6-base-dev-tools).
    local before after new=()
    before=$(in_chroot dpkg-query -W -f='${Package}\n' | sort)
    in_chroot apt-get install -y --no-install-recommends "${deps[@]}"
    after=$(in_chroot dpkg-query -W -f='${Package}\n' | sort)
    mapfile -t new < <(comm -13 <(echo "$before") <(echo "$after"))
    local rc=0
    in_chroot sh -c 'cd /tmp/krc \
        && cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr >/dev/null \
        && cmake --build build -j"$(nproc)" \
        && cd build && cpack -G DEB >/dev/null' || rc=1
    local deb=""
    ((rc == 0)) && deb=$(find "$CHROOT_DIR/tmp/krc/build" -maxdepth 1 -name 'kwin4_effect_shapecorners*.deb' | head -1)
    [[ -n $deb ]] && cp "$deb" "$CHROOT_DIR/tmp/roundcorners.deb"
    # narzędzia (i wszystko doinstalowane) -> "auto"; autoremove zostawi to, czego wymaga system
    log "Usuwanie narzędzi kompilacji"
    in_chroot apt-mark auto "${deps[@]}" "${new[@]}" >/dev/null
    # SuggestsImportant=false: inaczej "apt Suggests dpkg-dev" zatrzyma cały kompilator
    in_chroot apt-get autoremove -y --purge -o APT::AutoRemove::SuggestsImportant=false
    rm -rf "$CHROOT_DIR/tmp/krc"
    if [[ -z $deb ]]; then
        warn "Nie udało się zbudować efektu zaokrąglonych rogów"
        return 1
    fi
    in_chroot apt-get install -y /tmp/roundcorners.deb
    rm -f "$CHROOT_DIR/tmp/roundcorners.deb"
    ok "Zaokrąglone rogi okien zainstalowane"
}

stage_novaos() {
    log "Budowanie pakietów NovaOS"
    bash "$SCRIPT_DIR/make-debs.sh"

    chroot_mount
    policy_rc_block
    in_chroot apt-get update

    # pakiety dodane do list po etapie "packages" (szybka ścieżka przy przebudowie)
    local rec="--no-install-recommends"
    [[ $INSTALL_RECOMMENDS == yes ]] && rec="--install-recommends"
    # shellcheck disable=SC2046
    in_chroot apt-get install -y $rec $(read_list "$PROJECT_DIR"/config/packages/{base,desktop,apps,installer}.list)

    rm -rf "$CHROOT_DIR/tmp/novaos-debs"
    mkdir -p "$CHROOT_DIR/tmp/novaos-debs"
    cp "$DEBS_DIR"/novaos-*.deb "$CHROOT_DIR/tmp/novaos-debs/"
    log "Instalacja pakietów NovaOS"
    local debs=() f
    for f in "$DEBS_DIR"/novaos-*.deb; do debs+=("/tmp/novaos-debs/$(basename "$f")"); done
    in_chroot env NOVAOS_BUILD=1 apt-get install -y --reinstall "${debs[@]}"
    rm -rf "$CHROOT_DIR/tmp/novaos-debs"

    purge_unwanted

    if [[ $ENABLE_ROUNDED_CORNERS == yes ]]; then
        if ! in_chroot dpkg-query -W kwin4-effect-shapecorners >/dev/null 2>&1 \
           && ! in_chroot sh -c 'ls /usr/lib/x86_64-linux-gnu/qt6/plugins/kwin/effects/plugins/ 2>/dev/null | grep -q shapecorners'; then
            build_rounded_corners || warn "Efekt zaokrąglonych rogów niedostępny (system działa bez niego)"
        fi
    fi

    policy_rc_unblock
    chroot_umount
}
