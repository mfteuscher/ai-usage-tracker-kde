import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as Plasma5Support

PlasmoidItem {
    id: root
    property var usage: ({ providers: {} })
    property string collector: "ai-usage-tracker-collect --notifications " + (Plasmoid.configuration.notificationsEnabled ? "on" : "off")
    readonly property color themeTextColor: Kirigami.Theme.textColor
    readonly property bool useWhiteWordmarks: 0.2126 * themeTextColor.r + 0.7152 * themeTextColor.g + 0.0722 * themeTextColor.b > 0.5

    function provider(name) { return usage.providers && usage.providers[name] ? usage.providers[name] : ({ state: "unavailable" }) }
    function wordmark(providerName) { return Qt.resolvedUrl("../images/" + providerName + (useWhiteWordmarks ? "-dark.svg" : "-light.svg")) }
    function percent(item) { return item && item.usedPercent !== null && item.usedPercent !== undefined ? Math.max(0, Math.min(100, item.usedPercent)) : 0 }
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
    function refresh() {
        executor.disconnectSource(collector)
        executor.connectSource(collector)
    }

    Plasma5Support.DataSource {
        id: executor
        engine: "executable"
        onNewData: function(source, data) {
            if (source !== root.collector || !data["stdout"]) return
            try { root.usage = JSON.parse(data["stdout"]) } catch (error) { root.usage = ({ providers: {} }) }
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
    toolTipSubText: i18n("Claude: %1 · Codex: %2", countdown(provider("claude").primary ? provider("claude").primary.resetsAt : null), countdown(provider("codex").primary ? provider("codex").primary.resetsAt : null))

    compactRepresentation: MouseArea {
        // Keep the visible 94px bars separated from neighboring panel widgets.
        implicitWidth: 112
        implicitHeight: 30
        Layout.minimumWidth: 112
        Layout.preferredWidth: 112
        Layout.maximumWidth: 112
        onClicked: root.expanded = !root.expanded
        Column {
            anchors.centerIn: parent
            spacing: 3
            Repeater {
                model: [{ key: "claude", color: "#D97706" }, { key: "codex", color: "#2563EB" }]
                delegate: Rectangle {
                    required property var modelData
                    width: 94
                    height: 8
                    radius: height / 2
                    color: "#404040"
                    border.width: root.percent(root.provider(modelData.key).primary) >= 90 ? 1 : 0
                    border.color: "#DC2626"
                    Rectangle {
                        width: parent.width * root.percent(root.provider(modelData.key).primary) / 100
                        height: parent.height
                        radius: parent.radius
                        color: modelData.color
                    }
                }
            }
        }
    }

    fullRepresentation: ColumnLayout {
        implicitWidth: 360
        implicitHeight: 300
        spacing: 6
        Repeater {
            model: [{ key: "claude", title: i18n("Claude Code"), color: "#D97706" }, { key: "codex", title: i18n("OpenAI Codex"), color: "#2563EB" }]
            delegate: PlasmaComponents.GroupBox {
                required property var modelData
                Layout.fillWidth: true
                title: ""
                ColumnLayout {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    property var info: root.provider(modelData.key)
                    Image {
                        Layout.preferredWidth: 150
                        Layout.preferredHeight: 24
                        Layout.alignment: Qt.AlignLeft
                        source: root.wordmark(modelData.key)
                        fillMode: Image.PreserveAspectFit
                        horizontalAlignment: Image.AlignLeft
                        sourceSize.height: 48
                        mipmap: true
                    }
                    PlasmaComponents.Label {
                        Layout.fillWidth: true
                        visible: parent.info.state !== "fresh"
                        text: parent.info.message || i18n("Usage data is unavailable")
                        wrapMode: Text.WordWrap
                    }
                    Repeater {
                        model: [
                            { window: parent.info.primary, fallback: i18n("Session"), showUpdated: !parent.info.secondary },
                            { window: parent.info.secondary, fallback: i18n("Weekly"), showUpdated: !!parent.info.secondary }
                        ]
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            visible: modelData.window !== null && modelData.window !== undefined
                            RowLayout {
                                Layout.fillWidth: true
                                PlasmaComponents.Label { text: modelData.window ? (modelData.window.label || modelData.fallback) : "" }
                                Item { Layout.fillWidth: true }
                                PlasmaComponents.Label { text: Math.round(root.percent(modelData.window)) + "%" }
                            }
                            PlasmaComponents.ProgressBar {
                                Layout.fillWidth: true
                                value: root.percent(modelData.window) / 100
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                PlasmaComponents.Label {
                                    text: modelData.window ? root.countdown(modelData.window.resetsAt) : ""
                                    opacity: 0.7
                                }
                                PlasmaComponents.Label {
                                    text: modelData.window ? "(" + root.resetDateTime(modelData.window.resetsAt) + ")" : ""
                                    opacity: 0.5
                                }
                                Item { Layout.fillWidth: true }
                                PlasmaComponents.Label {
                                    visible: modelData.showUpdated && parent.parent.parent.info.lastUpdatedAt
                                    text: visible ? i18n("Updated %1", root.updatedTime(parent.parent.parent.info.lastUpdatedAt)) : ""
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
