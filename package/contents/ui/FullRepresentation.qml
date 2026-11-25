import QtQuick 2.15
import QtQuick.Layouts 1.15
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.plasma.components 3.0 as PlasmaComponents3
import org.kde.plasma.extras 2.0 as PlasmaExtras
import org.kde.kirigami 2.20 as Kirigami

PlasmaExtras.Representation {
    id: full
    property var applet
    readonly property bool dual: applet.secondary !== null
    readonly property string slot: dual && tabs.currentIndex === 1 ? "secondary" : "primary"
    readonly property var tunnel: slot === "secondary" ? applet.secondary : applet.primary
    readonly property bool switchable: tunnel.enabled !== undefined
    readonly property var current: {
        const profiles = tunnel.profiles || []
        for (let i = 0; i < profiles.length; i++) {
            if (profiles[i].id === tunnel.selected) return profiles[i]
        }
        return null
    }
    property bool hintVisible: false
    property bool warningDismissed: false

    implicitWidth: PlasmaCore.Units.gridUnit * 24
    implicitHeight: PlasmaCore.Units.gridUnit * 28
    collapseMarginsHint: true

    onSlotChanged: hintVisible = false
    Connections {
        target: full.applet
        function onWarningTextChanged() { full.warningDismissed = false }
    }

    readonly property bool on: applet.running && (!switchable || tunnel.enabled === true)
    readonly property var ping: {
        const result = applet.pings[slot]
        return result && result.profile === tunnel.selected ? result : null
    }

    function profileTitle(profile) {
        const aliases = profile.aliases || []
        return profile.title || (aliases.length ? aliases[0].name : profile.name)
    }

    function tunnelTitle() {
        if (current) return profileTitle(current)
        if (tunnel.selected === "none") return "Профиль не выбран"
        return "Профиль не определён"
    }

    function stateText() {
        if (!applet.known) return "Состояние неизвестно"
        if (!applet.running) return "Xray остановлен"
        return on ? "Включён" : "Выключен"
    }

    function flag(country) {
        if (!/^[A-Z]{2}$/.test(country)) return ""
        return String.fromCodePoint(0x1F1E6 + country.charCodeAt(0) - 65, 0x1F1E6 + country.charCodeAt(1) - 65) + " "
    }

    function toggle(on) {
        if (on && tunnel.selected === "none") {
            hintVisible = true
            return
        }
        applet.setEnabled(slot, on)
    }

    header: PlasmaExtras.PlasmoidHeading {
        leftPadding: PlasmaCore.Units.smallSpacing
        rightPadding: PlasmaCore.Units.smallSpacing
        contentItem: RowLayout {
            spacing: PlasmaCore.Units.smallSpacing
            PlasmaComponents3.TabBar {
                id: tabs
                visible: full.dual
                Layout.fillWidth: true
                PlasmaComponents3.TabButton { text: "Основной" }
                PlasmaComponents3.TabButton { text: "Дополнительный" }
            }
            PlasmaExtras.Heading {
                visible: !full.dual
                level: 3
                text: "Прокси Xray"
                Layout.fillWidth: true
            }
            PlasmaComponents3.ToolButton {
                id: restartButton
                visible: full.applet.running
                enabled: !full.applet.acting
                icon.name: "view-refresh"
                onClicked: full.applet.execute("restart")
                Accessible.name: "Перезапустить Xray"
                PlasmaComponents3.ToolTip { text: restartButton.Accessible.name }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: PlasmaCore.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: PlasmaCore.Units.largeSpacing
            Layout.rightMargin: PlasmaCore.Units.largeSpacing
            Layout.topMargin: PlasmaCore.Units.smallSpacing * 2
            spacing: PlasmaCore.Units.largeSpacing
            Kirigami.Icon {
                source: "network-vpn"
                opacity: full.on ? 1 : 0.4
                Layout.preferredWidth: PlasmaCore.Units.iconSizes.large
                Layout.preferredHeight: PlasmaCore.Units.iconSizes.large
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                PlasmaExtras.Heading {
                    level: 2
                    text: full.tunnelTitle()
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                RowLayout {
                    spacing: PlasmaCore.Units.smallSpacing
                    Rectangle {
                        width: PlasmaCore.Units.smallSpacing * 2
                        height: width
                        radius: width / 2
                        color: !full.applet.known ? Kirigami.Theme.disabledTextColor
                             : (full.on ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor)
                    }
                    PlasmaComponents3.Label {
                        text: full.stateText()
                        Layout.fillWidth: true
                    }
                }
            }
            PlasmaComponents3.BusyIndicator {
                visible: full.applet.acting && full.applet.pending.kind === "enable" && full.applet.pending.slot === full.slot
                Layout.preferredWidth: PlasmaCore.Units.iconSizes.medium
                Layout.preferredHeight: PlasmaCore.Units.iconSizes.medium
            }
            PlasmaComponents3.Switch {
                id: tunnelSwitch
                visible: full.switchable
                enabled: !full.applet.acting
                checked: full.tunnel.enabled === true
                onToggled: {
                    const wanted = checked
                    checked = Qt.binding(function() { return full.tunnel.enabled === true })
                    full.toggle(wanted)
                }
                Accessible.name: checked ? "Выключить туннель" : "Включить туннель"
                PlasmaComponents3.ToolTip { text: tunnelSwitch.Accessible.name }
            }
        }

        GridLayout {
            visible: full.switchable && full.tunnel.ports !== undefined
            Layout.fillWidth: true
            Layout.leftMargin: PlasmaCore.Units.largeSpacing * 2 + PlasmaCore.Units.iconSizes.large
            Layout.rightMargin: PlasmaCore.Units.largeSpacing
            columns: 3
            columnSpacing: PlasmaCore.Units.largeSpacing
            rowSpacing: 0

            PlasmaComponents3.Label { text: "HTTP"; opacity: 0.6 }
            CopyLabel {
                value: "127.0.0.1:" + (full.tunnel.ports ? full.tunnel.ports.http : "")
                opacity: full.on ? 1 : 0.5
                Layout.fillWidth: true
                Layout.columnSpan: 2
            }
            PlasmaComponents3.Label { text: "SOCKS"; opacity: 0.6 }
            CopyLabel {
                value: "127.0.0.1:" + (full.tunnel.ports ? full.tunnel.ports.socks : "")
                opacity: full.on ? 1 : 0.5
                Layout.fillWidth: true
                Layout.columnSpan: 2
            }
            PlasmaComponents3.Label { text: "Связь"; opacity: 0.6 }
            PlasmaComponents3.Label {
                text: full.applet.pingingSlot === full.slot ? "проверяю…"
                    : !full.on ? "—"
                    : !full.ping ? "не проверялась"
                    : (full.ping.ok ? full.ping.ms + " мс" : "нет связи") + " · в " + full.ping.at
                color: full.on && full.ping && !full.ping.ok && full.applet.pingingSlot !== full.slot ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                opacity: full.on && full.ping ? 1 : 0.6
                elide: Text.ElideRight
                Layout.fillWidth: true
                HoverHandler { id: pingHover }
                PlasmaComponents3.ToolTip {
                    visible: pingHover.hovered && full.ping !== null
                    text: "Время ответа google.com через этот туннель"
                }
            }
            PlasmaComponents3.ToolButton {
                text: "Пинг"
                enabled: full.on && full.applet.pingingSlot === ""
                onClicked: full.applet.ping(full.slot)
                PlasmaComponents3.ToolTip { text: "Проверить связь через этот туннель" }
            }
            PlasmaComponents3.Label {
                visible: exitAddress.visible
                text: "Выход"
                opacity: 0.6
            }
            RowLayout {
                id: exitAddress
                visible: full.on && full.ping !== null && full.ping.ok && full.ping.ip !== "" && full.applet.pingingSlot !== full.slot
                Layout.fillWidth: true
                Layout.columnSpan: 2
                spacing: 0
                PlasmaComponents3.Label {
                    visible: text !== ""
                    text: full.ping ? full.flag(full.ping.country) : ""
                }
                CopyLabel {
                    value: full.ping ? full.ping.ip : ""
                    Layout.fillWidth: true
                }
            }
        }

        Notice {
            shown: full.applet.known && !full.applet.running && !full.applet.acting
            type: Kirigami.MessageType.Warning
            text: "Xray остановлен — прокси недоступны."
            actions: [
                Kirigami.Action {
                    text: "Запустить"
                    icon.name: "media-playback-start"
                    enabled: !full.applet.acting
                    onTriggered: full.applet.execute("restart")
                }
            ]
        }
        Notice {
            shown: full.applet.acting
            type: Kirigami.MessageType.Information
            text: "Подтвердите действие в окне запроса пароля и дождитесь проверки…"
        }
        Notice {
            shown: full.hintVisible
            type: Kirigami.MessageType.Information
            text: "Выберите профиль в списке — туннель включится сам."
            showCloseButton: true
            onDismissed: full.hintVisible = false
        }
        Notice {
            shown: full.applet.errorText !== ""
            type: Kirigami.MessageType.Error
            text: full.applet.errorText
            showCloseButton: true
            onDismissed: full.applet.errorText = ""
        }
        Notice {
            shown: full.applet.warningText !== "" && !full.warningDismissed
            type: Kirigami.MessageType.Warning
            text: full.applet.warningText
            showCloseButton: true
            onDismissed: full.warningDismissed = true
        }

        PlasmaExtras.SearchField {
            id: search
            Layout.fillWidth: true
            Layout.leftMargin: PlasmaCore.Units.smallSpacing * 2
            Layout.rightMargin: PlasmaCore.Units.smallSpacing * 2
            placeholderText: "Найти профиль…"
            Keys.onDownPressed: profileList.focusFirst()
            onAccepted: profileList.chooseOnly()
        }

        ProfileList {
            id: profileList
            Layout.fillWidth: true
            Layout.fillHeight: true
            profiles: full.tunnel.profiles || []
            selectedId: full.tunnel.selected || ""
            query: search.text
            pendingId: full.applet.acting && full.applet.pending.slot === full.slot ? full.applet.pending.id : ""
            working: full.applet.acting
            onProfileChosen: function(profileId) { full.applet.select(full.slot, profileId) }
        }
    }
}
