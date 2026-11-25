import QtQuick 2.15
import QtQuick.Layouts 1.15
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.plasma.plasmoid 2.0

Item {
    id: root
    property bool running: false
    property bool known: false
    property bool busy: false
    property string pendingCommand: ""
    property string queuedCommand: ""
    property string errorText: ""
    property string warningText: ""
    property var pings: ({})
    property var primary: ({ selected: "", profiles: [] })
    property var secondary: null
    readonly property var pending: describe(pendingCommand)
    readonly property var queued: describe(queuedCommand)
    // Actions that change Xray and ask for the password; a ping or a status poll only reads.
    readonly property bool acting: (busy && changes(pending)) || changes(queued)
    readonly property string pingingSlot: busy && pending.kind === "ping" ? pending.slot : (queued.kind === "ping" ? queued.slot : "")

    readonly property string helper: '"$HOME/.local/bin/xray-widget" '
    readonly property color stateColor: !known || acting ? "#888888" : (running ? "#2eaf62" : "#d44848")

    function describe(command) {
        const parts = command.split(" ")
        if (parts[0] === "select") return { kind: "select", slot: "primary", id: parts[1] }
        if (parts[0] === "select-secondary") return { kind: "select", slot: "secondary", id: parts[1] }
        if (parts[0] === "enable") return { kind: "enable", slot: parts[1], id: "", on: parts[2] === "on" }
        if (parts[0] === "ping") return { kind: "ping", slot: parts[1], id: "" }
        if (parts[0] === "restart") return { kind: "restart", slot: "", id: "" }
        return { kind: "", slot: "", id: "" }
    }

    function changes(action) {
        return action.kind === "select" || action.kind === "enable" || action.kind === "restart"
    }

    function execute(command) {
        if (busy) {
            // A click during a background poll or ping must not be lost.
            if (command !== "status" && !changes(pending)) queuedCommand = command
            return
        }
        busy = true
        pendingCommand = command
        if (command !== "status") errorText = ""
        runner.connectSource(helper + command)
    }

    function select(slot, profileId) {
        if (/^[A-Za-z0-9_-]{1,80}$/.test(profileId))
            execute((slot === "secondary" ? "select-secondary " : "select ") + profileId)
    }

    function setEnabled(slot, enabled) {
        execute("enable " + slot + (enabled ? " on" : " off"))
    }

    function ping(slot) {
        execute("ping " + slot)
    }

    function remember(result) {
        const tunnel = result.slot === "secondary" ? secondary : primary
        const next = Object.assign({}, pings)
        next[result.slot] = { ok: result.ok, ms: result.ms || 0, ip: result.ip || "", country: result.country || "",
                              at: Qt.formatTime(new Date(), "hh:mm"), profile: tunnel ? tunnel.selected : "" }
        pings = next
    }

    function updateState(result) {
        root.running = result.running
        root.primary = { selected: result.selected, profiles: result.profiles, enabled: result.enabled, ports: result.ports }
        root.secondary = result.secondary || null
        root.warningText = result.warning || ""
        root.known = true
    }

    PlasmaCore.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: {
            disconnectSource(sourceName)
            const done = root.describe(root.pendingCommand)
            root.busy = false
            root.pendingCommand = ""
            let result = null
            try {
                result = JSON.parse(data.stdout)
            } catch (error) {
                result = { ok: false, error: "Не удалось получить состояние Xray" }
            }
            if (result.ok) {
                root.updateState(result)
                if (result.ping) root.remember(result.ping)
                // Check the link right after the tunnel got a new profile or was switched on.
                if ((done.kind === "select" || (done.kind === "enable" && done.on)) && root.queuedCommand === "")
                    root.queuedCommand = "ping " + done.slot
            } else if (done.kind === "") {
                root.known = false
                root.errorText = result.error || "Ошибка управления Xray"
            } else {
                root.errorText = result.error || "Ошибка управления Xray"
            }
            if (root.queuedCommand !== "") {
                const next = root.queuedCommand
                root.queuedCommand = ""
                root.execute(next)
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
    Plasmoid.toolTipSubText: acting ? "Выполняется действие" : (!known ? "Состояние неизвестно" : (running ? "Xray запущен" : "Xray остановлен"))

    Plasmoid.compactRepresentation: Item {
        implicitWidth: 24
        implicitHeight: 24
        Layout.minimumWidth: implicitWidth
        Layout.preferredWidth: implicitWidth
        Rectangle {
            anchors.centerIn: parent
            width: 12
            height: 12
            radius: 6
            color: root.stateColor
        }
        MouseArea { anchors.fill: parent; onClicked: plasmoid.expanded = !plasmoid.expanded }
    }

    Plasmoid.fullRepresentation: FullRepresentation {
        applet: root
    }
}
