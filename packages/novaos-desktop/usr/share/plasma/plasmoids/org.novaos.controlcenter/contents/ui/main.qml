// =====================================================================
//  NovaOS – Centrum sterowania (plasmoid Plasma 6)
//  Wszystkie przełączniki wykonują prawdziwe polecenia systemowe:
//    Wi-Fi        → nmcli radio wifi on|off
//    Bluetooth    → bluetoothctl power on|off
//    Tryb ciemny  → plasma-apply-colorscheme NovaDark|NovaLight
//    Światło nocne→ kwriteconfig6 kwinrc NightColor + przeładowanie KWin
//    Głośność     → wpctl (PipeWire)
// =====================================================================
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as P5Support

PlasmoidItem {
    id: root

    property bool wifiOn: false
    property bool btOn: false
    property bool darkOn: true
    property bool nightOn: false
    property int volume: 50
    property bool muted: false
    property var pending: ({})

    Plasmoid.icon: "configure"
    toolTipMainText: "Centrum sterowania"
    toolTipSubText: "Wi-Fi, Bluetooth, motyw, głośność"
    preferredRepresentation: compactRepresentation

    // ---------- wykonywanie poleceń
    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: function (source, data) {
            var cb = root.pending[source]
            delete root.pending[source]
            disconnectSource(source)
            if (cb) cb((data["stdout"] || "").trim(), data["exit code"])
        }
    }
    function run(cmd, cb) {
        // unikalny klucz – to samo polecenie może być wywołane wielokrotnie
        var key = cmd + " #" + Date.now() + Math.random()
        pending[key] = cb
        exec.connectSource(key)
    }

    function refresh() {
        run("nmcli radio wifi", function (out) { root.wifiOn = (out === "enabled") })
        run("bluetoothctl show 2>/dev/null | grep -q 'Powered: yes' && echo on || echo off",
            function (out) { root.btOn = (out === "on") })
        run("kreadconfig6 --file kdeglobals --group General --key ColorScheme",
            function (out) { root.darkOn = (out.indexOf("Light") < 0) })
        run("kreadconfig6 --file kwinrc --group NightColor --key Active",
            function (out) { root.nightOn = (out === "true") })
        run("wpctl get-volume @DEFAULT_AUDIO_SINK@", function (out) {
            var m = out.match(/Volume:\s*([0-9.]+)/)
            if (m) root.volume = Math.round(parseFloat(m[1]) * 100)
            root.muted = out.indexOf("MUTED") >= 0
        })
    }

    onExpandedChanged: if (expanded) refresh()
    Component.onCompleted: refresh()

    function setWifi(on) { run("nmcli radio wifi " + (on ? "on" : "off"), function () { refresh() }) }
    function setBt(on) { run("bluetoothctl power " + (on ? "on" : "off"), function () { refresh() }) }
    function setDark(on) {
        var scheme = on ? "NovaDark" : "NovaLight"
        var icons = on ? "Papirus-Dark" : "Papirus"
        run("plasma-apply-colorscheme " + scheme + " && kwriteconfig6 --file kdeglobals --group Icons --key Theme " + icons
            + " && dbus-send --session --type=signal /KIconLoader org.kde.KIconLoader.iconChanged int32:0",
            function () { refresh() })
    }
    function setNight(on) {
        run("kwriteconfig6 --file kwinrc --group NightColor --key Active " + (on ? "true" : "false")
            + " && dbus-send --session --type=method_call --dest=org.kde.KWin /KWin org.kde.KWin.reconfigure",
            function () { refresh() })
    }
    function setVolume(v) { run("wpctl set-volume @DEFAULT_AUDIO_SINK@ " + (v / 100).toFixed(2), function () {}) }
    function toggleMute() { run("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle", function () { refresh() }) }

    // ---------- ikona w panelu
    compactRepresentation: MouseArea {
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded
        Kirigami.Icon {
            anchors.fill: parent
            source: "configure"
            active: parent.containsMouse
        }
    }

    // ---------- panel rozwijany
    fullRepresentation: ColumnLayout {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 20
        Layout.preferredHeight: Kirigami.Units.gridUnit * 21
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            Kirigami.Icon { source: "novaos-start"; Layout.preferredWidth: Kirigami.Units.iconSizes.medium; Layout.preferredHeight: width }
            Kirigami.Heading { text: "Centrum sterowania"; level: 3; Layout.fillWidth: true }
            PC3.ToolButton { icon.name: "view-refresh"; onClicked: root.refresh(); PC3.ToolTip.text: "Odśwież"; PC3.ToolTip.visible: hovered }
        }

        GridLayout {
            columns: 2
            rowSpacing: Kirigami.Units.smallSpacing * 2
            columnSpacing: Kirigami.Units.smallSpacing * 2
            Layout.fillWidth: true

            Repeater {
                model: [
                    { name: "Wi-Fi", icon: "network-wireless", key: "wifi" },
                    { name: "Bluetooth", icon: "preferences-system-bluetooth", key: "bt" },
                    { name: "Tryb ciemny", icon: "weather-clear-night", key: "dark" },
                    { name: "Światło nocne", icon: "redshift-status-on", key: "night" }
                ]
                delegate: QQC2.AbstractButton {
                    id: tile
                    required property var modelData
                    readonly property bool on: modelData.key === "wifi" ? root.wifiOn
                                             : modelData.key === "bt" ? root.btOn
                                             : modelData.key === "dark" ? root.darkOn : root.nightOn
                    Layout.fillWidth: true
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 3.2
                    hoverEnabled: true
                    onClicked: {
                        if (modelData.key === "wifi") root.setWifi(!on)
                        else if (modelData.key === "bt") root.setBt(!on)
                        else if (modelData.key === "dark") root.setDark(!on)
                        else root.setNight(!on)
                    }
                    background: Rectangle {
                        radius: Kirigami.Units.cornerRadius * 2
                        color: tile.on ? Kirigami.Theme.highlightColor
                                       : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, tile.hovered ? 0.14 : 0.08)
                        Behavior on color { ColorAnimation { duration: 180 } }
                    }
                    contentItem: RowLayout {
                        spacing: Kirigami.Units.smallSpacing * 2
                        Kirigami.Icon {
                            source: tile.modelData.icon
                            Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                            Layout.preferredHeight: width
                            Layout.leftMargin: Kirigami.Units.largeSpacing
                            color: tile.on ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                        }
                        ColumnLayout {
                            spacing: 0
                            PC3.Label { text: tile.modelData.name; font.bold: true; color: tile.on ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor }
                            PC3.Label { text: tile.on ? "Włączone" : "Wyłączone"; opacity: 0.8; font.pointSize: Kirigami.Theme.smallFont.pointSize; color: tile.on ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor }
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            PC3.ToolButton { icon.name: root.muted ? "audio-volume-muted" : "audio-volume-high"; onClicked: root.toggleMute() }
            PC3.Slider {
                Layout.fillWidth: true
                from: 0; to: 100; stepSize: 1
                value: root.volume
                onMoved: { root.volume = value; root.setVolume(value) }
            }
            PC3.Label { text: root.volume + "%"; Layout.minimumWidth: Kirigami.Units.gridUnit * 2 }
        }

        Kirigami.Separator { Layout.fillWidth: true }

        GridLayout {
            columns: 4
            Layout.fillWidth: true
            Repeater {
                model: [
                    { name: "Ustawienia", icon: "nova-settings", cmd: "nova-settings" },
                    { name: "Zrzut", icon: "spectacle", cmd: "spectacle" },
                    { name: "Monitor", icon: "nova-monitor", cmd: "nova-monitor" },
                    { name: "Zablokuj", icon: "system-lock-screen", cmd: "loginctl lock-session" }
                ]
                delegate: PC3.ToolButton {
                    required property var modelData
                    Layout.fillWidth: true
                    display: QQC2.AbstractButton.TextUnderIcon
                    icon.name: modelData.icon
                    icon.width: Kirigami.Units.iconSizes.medium
                    icon.height: Kirigami.Units.iconSizes.medium
                    text: modelData.name
                    onClicked: { root.run(modelData.cmd + " >/dev/null 2>&1 &", function () {}); root.expanded = false }
                }
            }
        }
        Item { Layout.fillHeight: true }
    }
}
