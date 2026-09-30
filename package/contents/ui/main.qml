import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as Plasma5Support

PlasmoidItem {
    id: root
    property var usage: ({ providers: {} })
    readonly property string collectorCommand: "ai-usage-tracker-collect --notifications " + (Plasmoid.configuration.notificationsEnabled ? "on" : "off") + " --providers " + enabledProviderNames()
    readonly property color themeTextColor: Kirigami.Theme.textColor
    readonly property bool useWhiteWordmarks: 0.2126 * themeTextColor.r + 0.7152 * themeTextColor.g + 0.0722 * themeTextColor.b > 0.5
    readonly property color progressTrackColor: useWhiteWordmarks ? '#5f5f5f' : '#c0c0c0'
    readonly property int panelWidth: Math.max(80, Plasmoid.configuration.panelWidth || 112)
    readonly property int barWidth: Math.max(62, panelWidth - 18)

    // One window as a bar that starts full and drains as quota is spent. The mark
    // shows how much of the window's time is left, which is where even spending
    // would put the fill; a fill shorter than the mark is spending too fast.
    component UsageBar: Rectangle {
        id: bar
        required property var quota
        required property color fillColor
        readonly property var share: root.elapsedShare(quota)
        height: 8
        radius: height / 2
        color: root.progressTrackColor
        border.width: root.remaining(quota) <= 10 ? 1 : 0
        border.color: "#DC2626"
        Rectangle {
            width: bar.width * root.remaining(bar.quota) / 100
            height: bar.height
            radius: bar.radius
            color: bar.fillColor
        }
        Rectangle {
            visible: bar.share !== null
            x: (1 - (bar.share || 0)) * bar.width - width / 2
            y: -1
            width: 2
            height: bar.height + 2
            radius: 1
            color: root.themeTextColor
            opacity: 0.75
        }
    }

    function provider(name) { return usage.providers && usage.providers[name] ? usage.providers[name] : ({ state: "unavailable", windows: [] }) }
    function windows(info) { return info && info.windows ? info.windows : [] }
    function headlineWindow(name) { var list = windows(provider(name)); return list.length ? list[0] : null }
    function providerEnabled(name) {
        var configured = name === "claude" ? Plasmoid.configuration.showClaude : Plasmoid.configuration.showCodex
        return (configured === undefined ? true : configured) && provider(name).cliAvailable !== false
    }
    function enabledProviderNames() {
        var names = []
        if (Plasmoid.configuration.showClaude !== false) names.push("claude")
        if (Plasmoid.configuration.showCodex !== false) names.push("codex")
        return names.length ? names.join(",") : "none"
    }
    function visibleProviderModels() {
        return [
            { key: "claude", title: i18n("Claude Code"), color: "#D97706" },
            { key: "codex", title: i18n("OpenAI Codex"), color: "#2563EB" }
        ].filter(function(entry) { return root.providerEnabled(entry.key) })
    }
    function statusColor(info) { return info.state === "stale" ? "#EAB308" : "#DC2626" }
    function wordmark(providerName) { return Qt.resolvedUrl("../images/" + providerName + (useWhiteWordmarks ? "-dark.svg" : "-light.svg")) }
    function percent(item) { return item && item.usedPercent !== null && item.usedPercent !== undefined ? Math.max(0, Math.min(100, item.usedPercent)) : 0 }
    // Quota left in the window, 0..100; an unknown window reads as empty rather than full.
    function remaining(item) { return item ? 100 - percent(item) : 0 }
    // Elapsed share of the window, 0..1, or null when its length or reset is unknown.
    function elapsedShare(item) {
        if (!item || !item.resetsAt || !item.durationMinutes) return null
        var length = item.durationMinutes * 60
        return Math.max(0, Math.min(1, (length - (item.resetsAt - Date.now() / 1000)) / length))
    }
    // Usage against the clock; within five points of even spending counts as on pace.
    function pace(item) {
        var elapsed = elapsedShare(item)
        if (elapsed === null) return ""
        var gap = percent(item) - elapsed * 100
        return gap > 5 ? "ahead" : gap < -5 ? "under" : "on"
    }
    function paceLabel(item) {
        var value = pace(item)
        return value === "ahead" ? i18n("Ahead of pace") : value === "under" ? i18n("Under pace") : value === "on" ? i18n("On pace") : ""
    }
    function countdown(timestamp) {
        if (!timestamp) return i18n("Reset time unavailable")
        var seconds = Math.max(0, timestamp - Math.floor(Date.now() / 1000))
        var days = Math.floor(seconds / 86400)
        var hours = Math.floor(seconds / 3600)
        var minutes = Math.floor((seconds % 3600) / 60)
        if (days > 0) return i18n("Resets in %1d %2h", days, Math.floor((seconds % 86400) / 3600))
        return hours > 0 ? i18n("Resets in %1h %2m", hours, minutes) : i18n("Resets in %1m", minutes)
    }
    function resetDateTime(timestamp) {
        if (!timestamp) return ""
        return Qt.locale().toString(new Date(timestamp * 1000), "MMM d, h:mm AP")
    }
    function updatedTime(timestamp) {
        if (!timestamp) return ""
        return Qt.locale().toString(new Date(timestamp * 1000), "h:mm AP")
    }
    // Starts a collector run. While one is still running this is a no-op, so
    // Refresh now can't stack runs on top of the timer.
    function refresh() {
        executor.connectSource(collectorCommand)
    }

    Plasma5Support.DataSource {
        id: executor
        engine: "executable"
        onNewData: function(source, data) {
            // The engine hands a finished source's old output back to anyone who
            // reconnects to it, so release it now to make the next connect re-run.
            disconnectSource(source)
            if (source !== root.collectorCommand || !data["stdout"]) return
            // Keep the previous reading if the collector ever prints something unparsable.
            try { root.usage = JSON.parse(data["stdout"]) } catch (error) { }
        }
    }
    Timer {
        interval: Math.max(60, Plasmoid.configuration.refreshSeconds) * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    toolTipMainText: i18n("AI Usage Tracker")
    toolTipSubText: i18n("Claude: %1 · Codex: %2", countdown(headlineWindow("claude") ? headlineWindow("claude").resetsAt : null), countdown(headlineWindow("codex") ? headlineWindow("codex").resetsAt : null))

    compactRepresentation: MouseArea {
        // Keep the visible 94px bars separated from neighboring panel widgets.
        implicitWidth: root.panelWidth
        implicitHeight: 30
        Layout.minimumWidth: root.panelWidth
        Layout.preferredWidth: root.panelWidth
        Layout.maximumWidth: root.panelWidth
        onClicked: root.expanded = !root.expanded
        Column {
            anchors.centerIn: parent
            spacing: 3
            Repeater {
                model: root.visibleProviderModels()
                delegate: UsageBar {
                    required property var modelData
                    width: root.barWidth
                    quota: root.headlineWindow(modelData.key)
                    fillColor: modelData.color
                }
            }
        }
    }

    fullRepresentation: ColumnLayout {
        implicitWidth: 360
        Layout.minimumHeight: 300
        spacing: 6
        Repeater {
            model: root.visibleProviderModels()
            delegate: PlasmaComponents.GroupBox {
                id: card
                required property var modelData
                readonly property var info: root.provider(modelData.key)
                readonly property var windows: root.windows(info)
                Layout.fillWidth: true
                title: ""
                ColumnLayout {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    RowLayout {
                        Layout.fillWidth: true
                        Image {
                            Layout.preferredWidth: card.modelData.key === "claude" ? 112 : 89
                            Layout.preferredHeight: 24
                            Layout.alignment: Qt.AlignLeft
                            source: root.wordmark(card.modelData.key)
                            fillMode: Image.PreserveAspectFit
                            horizontalAlignment: Image.AlignLeft
                            sourceSize.height: 48
                            mipmap: true
                        }
                        Rectangle {
                            visible: card.info.state !== "fresh"
                            Layout.preferredWidth: 8
                            Layout.preferredHeight: 8
                            Layout.alignment: Qt.AlignTop
                            Layout.leftMargin: 4
                            Layout.topMargin: 3
                            radius: width / 2
                            color: root.statusColor(card.info)
                            HoverHandler { id: statusDotHover }
                            Controls.ToolTip.visible: statusDotHover.hovered
                            Controls.ToolTip.delay: 250
                            Controls.ToolTip.text: card.info.message || i18n("Usage data is unavailable.")
                        }
                        Item { Layout.fillWidth: true }
                    }
                    PlasmaComponents.Label {
                        visible: card.windows.length === 0
                        Layout.fillWidth: true
                        text: card.info.message || i18n("Usage data is unavailable.")
                        opacity: 0.7
                        wrapMode: Text.WordWrap
                    }
                    Repeater {
                        model: card.windows
                        delegate: ColumnLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            RowLayout {
                                Layout.fillWidth: true
                                PlasmaComponents.Label { text: modelData.label }
                                Item { Layout.fillWidth: true }
                                PlasmaComponents.Label {
                                    text: root.paceLabel(modelData)
                                    color: root.pace(modelData) === "ahead" ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
                                    opacity: root.pace(modelData) === "ahead" ? 1 : 0.65
                                    HoverHandler { id: paceHover }
                                    Controls.ToolTip.visible: paceHover.hovered && text !== ""
                                    Controls.ToolTip.delay: 250
                                    Controls.ToolTip.text: i18n("The line on the bar marks how much of the window's time is left. A bar shorter than the line is spending faster than the window elapses.")
                                }
                                PlasmaComponents.Label { text: i18n("%1% left", Math.round(root.remaining(modelData))) }
                            }
                            UsageBar {
                                Layout.fillWidth: true
                                Layout.topMargin: 2
                                Layout.bottomMargin: 2
                                quota: modelData
                                fillColor: card.modelData.color
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                PlasmaComponents.Label {
                                    text: root.countdown(modelData.resetsAt)
                                    opacity: 0.7
                                }
                                PlasmaComponents.Label {
                                    visible: !!modelData.resetsAt
                                    text: "(" + root.resetDateTime(modelData.resetsAt) + ")"
                                    opacity: 0.5
                                }
                                Item { Layout.fillWidth: true }
                                PlasmaComponents.Label {
                                    visible: index === card.windows.length - 1 && !!card.info.lastUpdatedAt
                                    text: visible ? i18n("Updated %1", root.updatedTime(card.info.lastUpdatedAt)) : ""
                                    opacity: 0.65
                                }
                            }
                        }
                    }
                }
            }
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents.Label {
                Layout.fillWidth: true
                text: i18n("Warnings are controlled in the widget settings.")
                opacity: 0.65
                wrapMode: Text.WordWrap
            }
            PlasmaComponents.Button {
                text: i18n("Refresh now")
                icon.name: "view-refresh"
                onClicked: root.refresh()
            }
        }
    }
}
