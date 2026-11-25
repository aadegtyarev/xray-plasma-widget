import QtQuick 2.15
import QtQuick.Layouts 1.15
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.plasma.components 3.0 as PlasmaComponents3
import org.kde.plasma.extras 2.0 as PlasmaExtras
import org.kde.kirigami 2.20 as Kirigami

PlasmaComponents3.ScrollView {
    id: control
    property var profiles: []
    property string selectedId: ""
    property string query: ""
    property string pendingId: ""
    property bool working: false
    property string shownRows: ""
    signal profileChosen(string profileId)

    // The stock list item draws its subtitle in the smallest font; these rows use the normal one and a larger title.
    readonly property real titleSize: PlasmaCore.Theme.defaultFont.pointSize + 2

    PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff
    contentWidth: availableWidth - contentItem.leftMargin - contentItem.rightMargin

    function unique(values) {
        return values.filter(function(value, index) { return value && values.indexOf(value) === index })
    }

    function row(profile) {
        const aliases = profile.aliases || []
        const sources = unique(aliases.map(function(alias) { return alias.source }))
        const available = profile.available !== false
        const active = profile.id === selectedId
        const title = profile.title || (aliases.length ? aliases[0].name : profile.name)
        let kind = unique([profile.transport, sources.join(", ")]).join(" · ")
        if (!available) kind = unique([profile.transport, "не поддерживается"]).join(" · ")
        let details = []
        if (!available) details = details.concat(profile.descriptions || [])
        if (profile.endpoint) details.push("Сервер " + profile.endpoint)
        const renamed = aliases.length > 1 || (aliases.length === 1 && aliases[0].name !== title)
        if (renamed) {
            aliases.forEach(function(alias) {
                details.push("«" + alias.name + "»" + (alias.source ? " — " + alias.source : ""))
            })
        }
        if (available) details = details.concat(profile.descriptions || [])
        return {
            profileId: profile.id,
            title: title,
            subtitle: (active ? "Используется · " : "") + kind,
            details: details.join("\n"),
            group: available ? (sources[0] || "") : "Недоступны",
            available: available,
            active: active,
        }
    }

    function rebuild() {
        const words = query.trim().toLocaleLowerCase()
        const rows = profiles.map(row).filter(function(item) {
            return (item.title + " " + item.subtitle + " " + item.details + " " + item.group).toLocaleLowerCase().indexOf(words) !== -1
        })
        const next = JSON.stringify(rows)
        if (next === shownRows) return
        shownRows = next
        rowsModel.clear()
        rows.forEach(function(item) { rowsModel.append(item) })
    }

    function focusFirst() {
        if (list.count === 0) return
        list.currentIndex = 0
        list.currentItem.forceActiveFocus()
    }

    function chooseOnly() {
        if (rowsModel.count === 1 && rowsModel.get(0).available && !rowsModel.get(0).active)
            profileChosen(rowsModel.get(0).profileId)
    }

    onProfilesChanged: rebuild()
    onSelectedIdChanged: rebuild()
    onQueryChanged: rebuild()
    Component.onCompleted: rebuild()

    contentItem: ListView {
        id: list
        model: ListModel { id: rowsModel }
        currentIndex: -1
        boundsBehavior: Flickable.StopAtBounds
        topMargin: PlasmaCore.Units.smallSpacing * 2
        bottomMargin: PlasmaCore.Units.smallSpacing * 2
        leftMargin: PlasmaCore.Units.smallSpacing * 2
        rightMargin: PlasmaCore.Units.smallSpacing * 2
        spacing: PlasmaCore.Units.smallSpacing
        highlight: PlasmaExtras.Highlight {}
        highlightMoveDuration: 0
        highlightResizeDuration: 0

        section.property: "group"
        section.delegate: Loader {
            active: section !== ""
            width: list.width - list.leftMargin - list.rightMargin
            height: active ? implicitHeight : 0
            sourceComponent: PlasmaComponents3.Label {
                text: section
                font.weight: Font.DemiBold
                font.pointSize: control.titleSize
                opacity: 0.7
                topPadding: PlasmaCore.Units.largeSpacing
                leftPadding: PlasmaCore.Units.smallSpacing
                bottomPadding: PlasmaCore.Units.smallSpacing
            }
        }

        delegate: Item {
            id: item
            property bool expanded: false
            readonly property bool busy: control.pendingId === model.profileId
            readonly property bool choosable: model.available && !model.active
            readonly property bool current: ListView.isCurrentItem

            width: list.width - list.leftMargin - list.rightMargin
            height: body.implicitHeight + PlasmaCore.Units.smallSpacing * 3
            activeFocusOnTab: true

            function choose() {
                if (choosable && !control.working) control.profileChosen(model.profileId)
            }

            Keys.onReturnPressed: choose()
            Keys.onEnterPressed: choose()
            Keys.onSpacePressed: expanded = !expanded
            onActiveFocusChanged: if (activeFocus) list.currentIndex = index

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                onEntered: list.currentIndex = index
                onClicked: if (model.details !== "") item.expanded = !item.expanded
                onDoubleClicked: item.choose()
            }

            ColumnLayout {
                id: body
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: PlasmaCore.Units.smallSpacing * 2
                anchors.rightMargin: PlasmaCore.Units.smallSpacing
                spacing: PlasmaCore.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true
                    spacing: PlasmaCore.Units.largeSpacing

                    Kirigami.Icon {
                        source: "network-vpn"
                        opacity: model.available ? 1 : 0.4
                        Layout.preferredWidth: PlasmaCore.Units.iconSizes.medium
                        Layout.preferredHeight: PlasmaCore.Units.iconSizes.medium
                        Kirigami.Icon {
                            visible: model.active || !model.available
                            source: model.active ? "emblem-checked" : "emblem-unavailable"
                            width: PlasmaCore.Units.iconSizes.small
                            height: width
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        PlasmaComponents3.Label {
                            text: model.title
                            font.pointSize: control.titleSize
                            font.weight: model.active ? Font.DemiBold : Font.Normal
                            opacity: model.available ? 1 : 0.6
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        PlasmaComponents3.Label {
                            text: model.subtitle
                            opacity: 0.7
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    PlasmaComponents3.BusyIndicator {
                        visible: item.busy
                        Layout.preferredWidth: PlasmaCore.Units.iconSizes.medium
                        Layout.preferredHeight: PlasmaCore.Units.iconSizes.medium
                    }
                    PlasmaComponents3.Button {
                        visible: item.choosable && item.current && !item.busy
                        enabled: !control.working
                        text: "Выбрать"
                        icon.name: "network-connect"
                        onClicked: item.choose()
                    }
                    PlasmaComponents3.ToolButton {
                        visible: model.details !== ""
                        icon.name: item.expanded ? "collapse" : "expand"
                        onClicked: item.expanded = !item.expanded
                        Accessible.name: item.expanded ? "Свернуть" : "Подробнее"
                        PlasmaComponents3.ToolTip { text: parent.Accessible.name }
                    }
                }

                PlasmaComponents3.Label {
                    visible: item.expanded
                    text: model.details
                    wrapMode: Text.Wrap
                    opacity: 0.8
                    Layout.fillWidth: true
                    Layout.leftMargin: PlasmaCore.Units.iconSizes.medium + PlasmaCore.Units.largeSpacing
                    Layout.bottomMargin: PlasmaCore.Units.smallSpacing
                }
            }
        }

        PlasmaExtras.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - PlasmaCore.Units.largeSpacing * 4
            visible: list.count === 0
            iconName: control.query.trim() !== "" ? "edit-none" : "network-vpn"
            text: control.query.trim() !== "" ? "Ничего не найдено" : "Профилей пока нет"
            explanation: control.query.trim() !== "" ? "" : "Добавьте группы в ~/.config/xray-widget/config.toml"
        }
    }
}
