// =====================================================================
//  NovaOS – domyślny układ pulpitu Plasma 6
//  Pływający pasek zadań na dole (dopasowany do zawartości), menu Start
//  z logo NovaOS, przypięte aplikacje Nova, centrum sterowania, zegar.
// =====================================================================

// ---- pulpit + tapeta
var allDesktops = desktops();
for (var i = 0; i < allDesktops.length; i++) {
    var d = allDesktops[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", "file:///usr/share/wallpapers/NovaOS/");
    d.writeConfig("FillMode", "2");
}

// ---- pasek zadań
var panel = new Panel;
panel.location = "bottom";
panel.height = 2 * Math.floor(gridUnit * 2.7 / 2);
panel.floating = true;
panel.alignment = "center";
panel.lengthMode = "fit";
panel.hiding = "none";

// Menu Start (Kickoff): wszystkie aplikacje, wyszukiwarka, ostatnie,
// profil użytkownika, przyciski uśpij/uruchom ponownie/wyłącz.
var kickoff = panel.addWidget("org.kde.plasma.kickoff");
kickoff.currentConfigGroup = ["Shortcuts"];
kickoff.writeConfig("global", "Alt+F1");
kickoff.currentConfigGroup = ["General"];
kickoff.writeConfig("icon", "novaos-start");
kickoff.writeConfig("favorites", [
    "nova-browser.desktop", "nova-files.desktop", "nova-terminal.desktop",
    "nova-store.desktop", "nova-settings.desktop", "nova-notes.desktop",
    "nova-music.desktop", "nova-gallery.desktop", "nova-calculator.desktop",
    "nova-monitor.desktop"
]);
kickoff.writeConfig("primaryActions", "1");          // przyciski zasilania
kickoff.writeConfig("showActionButtonCaptions", "true");
kickoff.writeConfig("systemFavorites", "lock-screen,logout,suspend,reboot,shutdown");
kickoff.writeConfig("highlightNewlyInstalledApps", "true");
kickoff.writeConfig("paneSwap", "false");

// Przypięte aplikacje
var tasks = panel.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", [
    "applications:nova-files.desktop",
    "applications:nova-browser.desktop",
    "applications:nova-terminal.desktop",
    "applications:nova-store.desktop",
    "applications:nova-settings.desktop"
]);
tasks.writeConfig("indicateAudioStreams", "true");
tasks.writeConfig("iconSpacing", "2");

panel.addWidget("org.kde.plasma.marginsseparator");

// Zasobnik systemowy (sieć, dźwięk, Bluetooth, bateria, powiadomienia)
var tray = panel.addWidget("org.kde.plasma.systemtray");

// Centrum sterowania NovaOS
panel.addWidget("org.novaos.controlcenter");

// Zegar z kalendarzem
var clock = panel.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", "true");
clock.writeConfig("dateFormat", "shortDate");
clock.writeConfig("use24hFormat", "2");
clock.writeConfig("showWeekNumbers", "true");

panel.addWidget("org.kde.plasma.showdesktop");
