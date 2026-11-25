import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC2
import QtQuick.Layouts 1.15
import org.kde.kirigami 2.20 as Kirigami

Kirigami.FormLayout {
    id: page
    property alias cfg_popupWidth: widthBox.value
    property alias cfg_popupHeight: heightBox.value

    function pixels(units) {
        return "≈ " + Math.round(units * Kirigami.Units.gridUnit) + " точек"
    }

    RowLayout {
        Kirigami.FormData.label: "Ширина окна:"
        QQC2.SpinBox {
            id: widthBox
            from: 18
            to: 80
        }
        QQC2.Label {
            text: page.pixels(widthBox.value)
            opacity: 0.7
        }
    }

    RowLayout {
        Kirigami.FormData.label: "Высота окна:"
        QQC2.SpinBox {
            id: heightBox
            from: 16
            to: 80
        }
        QQC2.Label {
            text: page.pixels(heightBox.value)
            opacity: 0.7
        }
    }

    QQC2.Label {
        Kirigami.FormData.isSection: true
        text: "Размер задаётся в единицах сетки Plasma и растёт вместе со шрифтом и масштабом экрана."
        wrapMode: Text.Wrap
        opacity: 0.7
        Layout.maximumWidth: Kirigami.Units.gridUnit * 20
    }
}
