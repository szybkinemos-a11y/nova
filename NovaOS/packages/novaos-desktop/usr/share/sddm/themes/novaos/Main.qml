// =====================================================================
//  NovaOS – ekran logowania (SDDM, Qt 6)
//  Kontekst SDDM: sddm, userModel, sessionModel, config, keyboard
// =====================================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects

Rectangle {
    id: root
    width: 1920
    height: 1080
    color: "#0B0B1A"

    readonly property color accent: config.accent ? config.accent : "#7B61FF"
    property int userIndex: userModel.lastIndex >= 0 ? userModel.lastIndex : 0
    property int sessionIdx: sessionModel.lastIndex >= 0 ? sessionModel.lastIndex : 0
    property string currentUser: userModel.lastUser

    function doLogin() {
        if (busy.running) return
        errorText.text = ""
        busy.running = true
        sddm.login(root.currentUser, password.text, root.sessionIdx)
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            busy.running = false
            errorText.text = qsTr("Nieprawidłowe hasło. Spróbuj ponownie.")
            password.text = ""
            password.forceActiveFocus()
            shake.restart()
        }
        function onLoginSucceeded() { fadeOut.start() }
    }

    // ---------- tło z rozmyciem
    Image {
        id: bg
        anchors.fill: parent
        source: config.background ? config.background : "background.png"
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
        visible: false
    }
    MultiEffect {
        anchors.fill: bg
        source: bg
        blurEnabled: true
        blur: config.blur ? parseFloat(config.blur) : 0.65
        blurMax: 48
        brightness: -0.12
        saturation: 0.1
    }

    // ---------- zegar
    ColumnLayout {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.12
        spacing: 0
        Text {
            id: clock
            Layout.alignment: Qt.AlignHCenter
            color: "white"
            font.family: "Inter"
            font.pixelSize: Math.round(root.height * 0.11)
            font.weight: Font.Light
            text: Qt.formatTime(new Date(), "HH:mm")
        }
        Text {
            id: date
            Layout.alignment: Qt.AlignHCenter
            color: "#D9D6F0"
            font.family: "Inter"
            font.pixelSize: Math.round(root.height * 0.022)
            text: Qt.locale().toString(new Date(), "dddd, d MMMM")
        }
        Timer {
            interval: 1000; running: true; repeat: true
            onTriggered: {
                clock.text = Qt.formatTime(new Date(), "HH:mm")
                date.text = Qt.locale().toString(new Date(), "dddd, d MMMM")
            }
        }
    }

    // ---------- karta logowania
    Rectangle {
        id: card
        width: 400
        height: cardCol.implicitHeight + 64
        anchors.centerIn: parent
        anchors.verticalCenterOffset: root.height * 0.08
        radius: 28
        color: Qt.rgba(0.08, 0.07, 0.16, 0.55)
        border.color: Qt.rgba(1, 1, 1, 0.12)
        border.width: 1

        SequentialAnimation {
            id: shake
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: -14; duration: 50 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: 14; duration: 80 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: -8; duration: 70 }
            NumberAnimation { target: card; property: "anchors.horizontalCenterOffset"; to: 0; duration: 60 }
        }

        ColumnLayout {
            id: cardCol
            anchors.fill: parent
            anchors.margins: 32
            spacing: 16

            // lista użytkowników (awatary)
            ListView {
                id: users
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredHeight: 128
                Layout.preferredWidth: Math.min(count, 3) * 110
                orientation: ListView.Horizontal
                model: userModel
                currentIndex: root.userIndex
                interactive: count > 3
                clip: true
                delegate: Item {
                    width: 110; height: 128
                    required property int index
                    required property string name
                    required property string realName
                    required property string icon
                    readonly property bool selected: ListView.isCurrentItem

                    Rectangle {
                        id: ring
                        width: selected ? 92 : 72; height: width
                        radius: width / 2
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: selected ? 0 : 10
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: "#A855F7" }
                            GradientStop { position: 1; color: "#3B82F6" }
                        }
                        opacity: selected ? 1 : 0.5
                        Behavior on width { NumberAnimation { duration: 160 } }

                        Rectangle {
                            id: avatarBg
                            anchors.fill: parent
                            anchors.margins: 3
                            radius: width / 2
                            color: "#1E1B33"
                            Text {
                                anchors.centerIn: parent
                                text: (realName || name).charAt(0).toUpperCase()
                                color: "white"
                                font.pixelSize: parent.width * 0.42
                                font.weight: Font.DemiBold
                                visible: avatar.status !== Image.Ready
                            }
                            Image {
                                id: avatar
                                anchors.fill: parent
                                source: icon
                                sourceSize: Qt.size(width * 2, height * 2)
                                fillMode: Image.PreserveAspectCrop
                                visible: false
                            }
                            Rectangle { id: mask; anchors.fill: parent; radius: width / 2; visible: false; layer.enabled: true }
                            MultiEffect {
                                anchors.fill: avatar
                                source: avatar
                                maskEnabled: true
                                maskSource: mask
                                visible: avatar.status === Image.Ready
                            }
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        text: realName || name
                        color: "white"
                        opacity: selected ? 1 : 0.6
                        font.family: "Inter"
                        font.pixelSize: 15
                        font.weight: selected ? Font.DemiBold : Font.Normal
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            users.currentIndex = index
                            root.currentUser = name
                            password.forceActiveFocus()
                        }
                    }
                }
                Component.onCompleted: {
                    if (root.currentUser === "" && count > 0) root.currentUser = userModel.data(userModel.index(0, 0), Qt.UserRole + 1)
                }
            }

            TextField {
                id: password
                objectName: "password"
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                echoMode: TextInput.Password
                placeholderText: qsTr("Hasło")
                placeholderTextColor: "#A9A5C4"
                color: "white"
                font.family: "Inter"
                font.pixelSize: 16
                leftPadding: 20
                rightPadding: 56
                focus: true
                background: Rectangle {
                    radius: 24
                    color: Qt.rgba(1, 1, 1, 0.08)
                    border.width: password.activeFocus ? 2 : 1
                    border.color: password.activeFocus ? root.accent : Qt.rgba(1, 1, 1, 0.2)
                }
                Keys.onReturnPressed: root.doLogin()
                Keys.onEnterPressed: root.doLogin()

                Rectangle {
                    id: goBtn
                    width: 40; height: 40; radius: 20
                    anchors.right: parent.right
                    anchors.rightMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: goArea.containsMouse ? Qt.lighter(root.accent, 1.15) : root.accent
                    Text {
                        anchors.centerIn: parent
                        text: busy.running ? "" : "→"
                        color: "white"
                        font.pixelSize: 20
                    }
                    BusyIndicator { id: busy; anchors.centerIn: parent; width: 28; height: 28; running: false }
                    MouseArea { id: goArea; anchors.fill: parent; hoverEnabled: true; onClicked: root.doLogin() }
                }
            }

            Text {
                id: errorText
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                color: "#FCA5A5"
                font.family: "Inter"
                font.pixelSize: 13
                visible: text !== ""
            }

            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                color: "#FBBF24"
                font.pixelSize: 12
                text: qsTr("Caps Lock jest włączony")
                visible: keyboard.capsLock
            }

            ComboBox {
                id: session
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                model: sessionModel
                textRole: "name"
                currentIndex: root.sessionIdx
                onActivated: function (i) { root.sessionIdx = i }
                visible: count > 1
                font.family: "Inter"
                background: Rectangle { radius: 18; color: Qt.rgba(1, 1, 1, 0.06); border.color: Qt.rgba(1, 1, 1, 0.12) }
                contentItem: Text { leftPadding: 16; text: session.displayText; color: "#D9D6F0"; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter }
            }
        }
    }

    // ---------- logo w lewym dolnym rogu
    Row {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 32
        spacing: 12
        Image { source: config.logo ? config.logo : "logo.png"; width: 40; height: 40; sourceSize: Qt.size(80, 80) }
        Text { text: "NovaOS"; color: "white"; font.family: "Inter"; font.pixelSize: 22; font.weight: Font.Bold; anchors.verticalCenter: parent.verticalCenter }
    }

    // ---------- przyciski zasilania w prawym dolnym rogu
    Row {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 32
        spacing: 12
        Repeater {
            model: [
                { label: qsTr("Uśpij"), glyph: "☾", act: "suspend", enabled: sddm.canSuspend },
                { label: qsTr("Uruchom ponownie"), glyph: "↻", act: "reboot", enabled: sddm.canReboot },
                { label: qsTr("Wyłącz"), glyph: "⏻", act: "poweroff", enabled: sddm.canPowerOff }
            ]
            delegate: Rectangle {
                required property var modelData
                width: 48; height: 48; radius: 24
                visible: modelData.enabled
                color: pArea.containsMouse ? Qt.rgba(1, 1, 1, 0.18) : Qt.rgba(1, 1, 1, 0.08)
                border.color: Qt.rgba(1, 1, 1, 0.15)
                Text { anchors.centerIn: parent; text: modelData.glyph; color: "white"; font.pixelSize: 20 }
                ToolTip.visible: pArea.containsMouse
                ToolTip.text: modelData.label
                MouseArea {
                    id: pArea
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        if (modelData.act === "suspend") sddm.suspend()
                        else if (modelData.act === "reboot") sddm.reboot()
                        else sddm.powerOff()
                    }
                }
            }
        }
    }

    NumberAnimation { id: fadeOut; target: root; property: "opacity"; to: 0; duration: 300 }
    Component.onCompleted: password.forceActiveFocus()
}
