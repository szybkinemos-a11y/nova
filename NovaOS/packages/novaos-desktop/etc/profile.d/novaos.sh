# NovaOS – zmienne środowiskowe dla wszystkich powłok
export NOVAOS=1
# Aplikacje Flatpak w menu (Flatpak sam dodaje XDG_DATA_DIRS, to zabezpieczenie)
case ":${XDG_DATA_DIRS:-}:" in
    *":/var/lib/flatpak/exports/share:"*) ;;
    *) export XDG_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}:/var/lib/flatpak/exports/share" ;;
esac
