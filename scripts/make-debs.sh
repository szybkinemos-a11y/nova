#!/usr/bin/env bash
# =====================================================================
#  Buduje pakiety NovaOS (.deb): novaos-desktop, novaos-apps,
#  novaos-installer. Nie wymaga root. Wynik: $WORK_DIR/debs/
#     ./scripts/make-debs.sh
# =====================================================================
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../build.conf
source "$SCRIPT_DIR/../build.conf"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"
require_cmds dpkg-deb python3 rsvg-convert rsync

BRAND="$WORK_DIR/brand"
ROOTS="$WORK_DIR/pkgroot"
mkdir -p "$DEBS_DIR" "$ROOTS"
rm -f "$DEBS_DIR"/novaos-*.deb

step "Generowanie brandingu (logo, ikony, tapety)"
python3 "$PROJECT_DIR/branding/generate.py" "$BRAND" >/dev/null
ok "Branding: $(find "$BRAND" -name '*.png' | wc -l) plików PNG"

copy_tree() {  # copy_tree <pakiet> -> katalog roboczy pakietu
    local pkg=$1 dst="$ROOTS/$1"
    rm -rf "$dst"
    mkdir -p "$dst"
    rsync -a --exclude templates --exclude '__pycache__' "$PROJECT_DIR/packages/$pkg/" "$dst/"
    echo "$dst"
}

finalize_pkg() {  # finalize_pkg <katalog> – szablony, uprawnienia, rozmiar, dpkg-deb
    local dst=$1 name f
    name=$(basename "$dst")
    # podstaw @ZMIENNE@ we wszystkich plikach tekstowych, które je zawierają
    while IFS= read -r -d '' f; do
        render_template "$f" "$f.tmp" && cat "$f.tmp" > "$f" && rm -f "$f.tmp"
    done < <(grep -rlZ --exclude='*.png' '@DISTRO_\|@UBUNTU_' "$dst" || true)
    find "$dst" -type d -exec chmod 755 {} +
    find "$dst" -type f ! -perm -u+x -exec chmod 644 {} +
    find "$dst" -type f -perm -u+x -exec chmod 755 {} +
    # pliki w /etc są plikami konfiguracyjnymi (dpkg zachowa zmiany użytkownika)
    if [[ -d "$dst/etc" ]]; then
        (cd "$dst" && find etc -type f | sed 's|^|/|' | sort) > "$dst/DEBIAN/conffiles"
        chmod 644 "$dst/DEBIAN/conffiles"
    fi
    local size
    size=$(du -sk --exclude=DEBIAN "$dst" | cut -f1)
    sed -i "/^Installed-Size:/d" "$dst/DEBIAN/control"
    echo "Installed-Size: $size" >> "$dst/DEBIAN/control"
    dpkg-deb --root-owner-group -Zxz --build "$dst" "$DEBS_DIR/${name}_${DISTRO_VERSION}_all.deb" >/dev/null
    ok "$name ($(du -h "$DEBS_DIR/${name}_${DISTRO_VERSION}_all.deb" | cut -f1))"
}

# ------------------------------------------------------------ novaos-desktop
step "Pakiet novaos-desktop"
D=$(copy_tree novaos-desktop)
while read -r src dst; do
    [[ -z $src || $src == \#* ]] && continue
    mkdir -p "$(dirname "$D/$dst")"
    render_template "$PROJECT_DIR/packages/novaos-desktop/templates/$src" "$D/$dst"
done < "$PROJECT_DIR/packages/novaos-desktop/templates/MAP"
mkdir -p "$D/usr/share/icons" "$D/usr/share/wallpapers" "$D/usr/share/pixmaps"
cp -r "$BRAND/icons/hicolor" "$D/usr/share/icons/"
cp -r "$BRAND/wallpapers/NovaOS" "$D/usr/share/wallpapers/"
cp "$BRAND"/plymouth/*.png "$D/usr/share/plymouth/themes/novaos/"
cp "$BRAND"/grub/*.png "$D/usr/share/grub/themes/novaos/"
cp "$BRAND"/sddm/*.png "$D/usr/share/sddm/themes/novaos/"
cp "$BRAND/logo/novaos-logo-256.png" "$D/usr/share/pixmaps/novaos-logo.png"
cp "$BRAND"/logo/*.png "$D/usr/share/novaos/"
LNF="$D/usr/share/plasma/look-and-feel/org.novaos.desktop/contents"
mkdir -p "$LNF/previews" "$LNF/splash/images"
cp "$BRAND/lookandfeel/preview.png" "$LNF/previews/preview.png"
cp "$BRAND/lookandfeel/fullscreenpreview.jpg.png" "$LNF/previews/fullscreenpreview.jpg"
cp "$BRAND/lookandfeel/splash-logo.png" "$LNF/splash/images/logo.png"
cp "$BRAND/sddm/background.png" "$LNF/splash/images/background.png"
finalize_pkg "$D"

# ------------------------------------------------------------ novaos-apps
step "Pakiet novaos-apps"
A=$(copy_tree novaos-apps)
PY="$A/usr/lib/novaos/python"
mkdir -p "$PY" "$A/usr/bin" "$A/usr/share/applications" "$A/usr/libexec/novaos" "$A/usr/share/polkit-1/actions"
for mod in "$PROJECT_DIR"/apps/novakit "$PROJECT_DIR"/apps/nova_*; do
    rsync -a --exclude '__pycache__' "$mod" "$PY/"
done
for mod in "$PROJECT_DIR"/apps/nova_*; do
    name=$(basename "$mod")           # nova_browser
    bin="${name//_/-}"                # nova-browser
    cat > "$A/usr/bin/$bin" <<LAUNCHER
#!/bin/sh
# Uruchamia $bin (NovaOS)
export PYTHONPATH=/usr/lib/novaos/python\${PYTHONPATH:+:\$PYTHONPATH}
exec /usr/bin/python3 -m $name "\$@"
LAUNCHER
    chmod 755 "$A/usr/bin/$bin"
done
cp "$PROJECT_DIR"/apps/desktop/*.desktop "$A/usr/share/applications/"
install -m755 "$PROJECT_DIR/apps/system/nova-helper" "$A/usr/libexec/novaos/nova-helper"
install -m644 "$PROJECT_DIR/apps/system/org.novaos.helper.policy" "$A/usr/share/polkit-1/actions/"
finalize_pkg "$A"

# ------------------------------------------------------------ novaos-installer
step "Pakiet novaos-installer"
I=$(copy_tree novaos-installer)
B="$I/etc/calamares/branding/novaos"
cp "$BRAND/calamares/logo.png" "$BRAND/calamares/welcome.png" "$BRAND/calamares/languages.png" "$B/"
finalize_pkg "$I"

step "Pakiety gotowe w $DEBS_DIR"
ls -1 "$DEBS_DIR"
