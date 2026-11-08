// NovaOS – pokaz slajdów podczas instalacji (Calamares, slideshowAPI 2)
import QtQuick
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 7000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    component NovaSlide: Slide {
        id: s
        property string heading
        property string body
        property string glyph
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#1E1240" }
                GradientStop { position: 1.0; color: "#0E1B3D" }
            }
            radius: 18
        }
        Column {
            anchors.centerIn: parent
            width: parent.width * 0.78
            spacing: 18
            Text { text: s.glyph; font.pixelSize: 64; color: "white"; anchors.horizontalCenter: parent.horizontalCenter }
            Text {
                text: s.heading; color: "white"; font.pixelSize: 30; font.bold: true
                width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            }
            Text {
                text: s.body; color: "#D9D6F0"; font.pixelSize: 17
                width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            }
        }
    }

    NovaSlide { glyph: "✦"; heading: "Witaj w NovaOS"; body: "Nowoczesny, szybki i prywatny system oparty na Ubuntu LTS i KDE Plasma 6." }
    NovaSlide { glyph: "🛍"; heading: "Nova Store"; body: "Tysiące aplikacji z repozytoriów Ubuntu i Flathub – instalacja jednym kliknięciem." }
    NovaSlide { glyph: "⚙"; heading: "Wszystko pod kontrolą"; body: "Nova Settings: motyw jasny i ciemny, kolor akcentu, Wi-Fi, Bluetooth, użytkownicy i aktualizacje." }
    NovaSlide { glyph: "🔒"; heading: "Bezpieczeństwo"; body: "Zapora sieciowa, automatyczne poprawki bezpieczeństwa, szyfrowanie dysku i brak telemetrii." }
    NovaSlide { glyph: "⌨"; heading: "Dla zaawansowanych"; body: "Nova Terminal i polecenie „nova”: nova update, nova install, nova doctor." }

    function onActivate() { presentation.currentSlide = 0 }
    function onLeave() { }
}
