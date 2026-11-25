import QtQuick 2.15
import QtQuick.Layouts 1.15
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.kirigami 2.20 as Kirigami

Kirigami.InlineMessage {
    id: notice
    property bool shown: false
    signal dismissed()

    Layout.fillWidth: true
    Layout.leftMargin: PlasmaCore.Units.smallSpacing * 2
    Layout.rightMargin: PlasmaCore.Units.smallSpacing * 2
    visible: shown
    // The close button assigns visible directly; restore the binding so the next message shows again.
    onVisibleChanged: if (!visible && shown) {
        dismissed()
        visible = Qt.binding(function() { return notice.shown })
    }
}
