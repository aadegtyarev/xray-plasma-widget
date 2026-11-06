import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls 2.15 as Controls
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.plasma.plasmoid 2.0

Item {
    id: root
    property bool running: false
    property bool known: false
    property bool busy: false
    property string currentProfile: ""
    property string errorText: ""
    property var profiles: []
    readonly property string helper: '"$HOME/.local/bin/xray-widget" '
    readonly property color stateColor: !known ? "#888888" : (running ? "#2eaf62" : "#d44848")

    function execute(command) {
        if (busy) return
        busy = true
        runner.connectSource(helper + command)
    }

    function updateState(result) {
        root.running = result.running
        root.currentProfile = result.selected
        root.profiles = result.profiles
        root.known = true
        let index = -1
        for (let i = 0; i < profiles.length; i++) {
            if (profiles[i].id === currentProfile) index = i
        }
        selector.currentIndex = index
    }

    PlasmaCore.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: {
            disconnectSource(sourceName)
            root.busy = false
            try {
                let result = JSON.parse(data.stdout)
                if (result.ok) {
                    root.updateState(result)
                    if (sourceName !== root.helper + "status") root.errorText = ""
                } else {
                    root.known = false
                    root.errorText = result.error || "Ошибка управления Xray"
                }
            } catch (error) {
                root.errorText = "Не удалось получить состояние Xray"
                root.known = false
            }
        }
    }

    Timer {
        interval: 10000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.execute("status")
    }

    Plasmoid.toolTipMainText: "Прокси Xray"
    Plasmoid.toolTipSubText: !known ? "Состояние неизвестно" : (running ? "Xray запущен" : "Xray остановлен")

    Plasmoid.compactRepresentation: Item {
        implicitWidth: compactRow.implicitWidth + 12
        implicitHeight: compactRow.implicitHeight + 8
        RowLayout {
            id: compactRow
            anchors.centerIn: parent
            spacing: 5
            Rectangle { width: 9; height: 9; radius: 5; color: root.stateColor }
            Controls.Label { text: "Xray" }
        }
        MouseArea { anchors.fill: parent; onClicked: plasmoid.expanded = !plasmoid.expanded }
    }

    Plasmoid.fullRepresentation: Item {
        Layout.minimumWidth: 280
        Layout.preferredWidth: 300
        Layout.minimumHeight: content.implicitHeight + 20
        ColumnLayout {
            id: content
            anchors.fill: parent
            anchors.margins: 10
            spacing: 8
            RowLayout {
                Rectangle { width: 10; height: 10; radius: 5; color: root.stateColor }
                Controls.Label {
                    text: !root.known ? "Состояние неизвестно" : (root.running ? "Xray запущен" : "Xray остановлен")
                    Layout.fillWidth: true
                }
            }
            Controls.Label {
                text: "Состояние процесса, не проверка интернета"
                font.pixelSize: 11
                opacity: 0.75
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Controls.ComboBox {
                    id: selector
                    Layout.fillWidth: true
                    enabled: !root.busy && root.profiles.length > 0
                    model: root.profiles
                    textRole: "name"
                    onActivated: {
                        let id = root.profiles[index].id
                        if (/^[A-Za-z0-9_-]{1,80}$/.test(id) && id !== root.currentProfile)
                            root.execute("select " + id)
                    }
                }
                Controls.Button {
                    text: root.running ? "Перезапустить" : "Запустить"
                    enabled: !root.busy
                    onClicked: root.execute("restart")
                }
            }
            Controls.Label {
                visible: root.errorText !== ""
                text: root.errorText
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
