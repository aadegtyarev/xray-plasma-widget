import QtQuick 2.15
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.plasma.components 3.0 as PlasmaComponents3

// A value the user often pastes elsewhere: a click puts it on the clipboard.
PlasmaComponents3.Label {
    id: control
    property string value: ""
    property bool copied: false

    text: copied ? "Скопировано" : value
    font.underline: area.containsMouse && !copied
    elide: Text.ElideRight

    TextEdit {
        id: clipboard
        visible: false
    }

    Timer {
        id: reset
        interval: 1500
        onTriggered: control.copied = false
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            clipboard.text = control.value
            clipboard.selectAll()
            clipboard.copy()
            control.copied = true
            reset.restart()
        }
    }

    PlasmaComponents3.ToolTip {
        visible: area.containsMouse && !control.copied
        text: "Скопировать " + control.value
    }
}
