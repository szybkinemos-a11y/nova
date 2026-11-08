// NovaOS – ekran ładowania po zalogowaniu (KSplash, Plasma 6)
import QtQuick

Rectangle {
    id: root
    color: "#0B0B1A"
    property int stage

    onStageChanged: {
        if (stage === 2) { intro.running = true }
        if (stage === 5) { outro.running = true }
    }

    Image {
        anchors.fill: parent
        source: "images/background.png"
        fillMode: Image.PreserveAspectCrop
        opacity: 0.55
    }

    Item {
        id: content
        anchors.centerIn: parent
        width: 320; height: 320
        opacity: 0

        Image {
            id: logo
            anchors.horizontalCenter: parent.horizontalCenter
            y: 30
            source: "images/logo.png"
            width: 140; height: 140
            sourceSize: Qt.size(280, 280)
            RotationAnimator on rotation {
                from: -6; to: 6; duration: 1600
                loops: Animation.Infinite
                easing.type: Easing.InOutSine
                running: true
            }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: logo.bottom
            anchors.topMargin: 22
            text: "NovaOS"
            color: "white"
            font.family: "Inter"
            font.pixelSize: 34
            font.weight: Font.Bold
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            spacing: 10
            Repeater {
                model: 3
                Rectangle {
                    width: 9; height: 9; radius: 4.5
                    color: index === 1 ? "#7B61FF" : (index === 0 ? "#A855F7" : "#3B82F6")
                    SequentialAnimation on opacity {
                        loops: Animation.Infinite
                        PauseAnimation { duration: index * 180 }
                        NumberAnimation { from: 0.25; to: 1; duration: 450 }
                        NumberAnimation { from: 1; to: 0.25; duration: 450 }
                        PauseAnimation { duration: (2 - index) * 180 }
                    }
                }
            }
        }
    }

    OpacityAnimator { id: intro; target: content; from: 0; to: 1; duration: 600; easing.type: Easing.OutCubic }
    OpacityAnimator { id: outro; target: root; from: 1; to: 0; duration: 400; easing.type: Easing.InCubic }
}
