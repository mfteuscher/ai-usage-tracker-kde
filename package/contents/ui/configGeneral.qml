import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as Plasma5Support

Item {
    id: configPage
    implicitWidth: 380
    implicitHeight: content.implicitHeight + Kirigami.Units.largeSpacing * 2

    property alias cfg_refreshSeconds: refresh.value
    property alias cfg_notificationsEnabled: notifications.checked
    property alias cfg_panelWidth: panelWidth.value
    property alias cfg_showClaude: showClaude.checked
    property alias cfg_showCodex: showCodex.checked
    property alias cfg_claudeUsageScraper: claudeUsageScraper.checked
    property int cfg_refreshSecondsDefault: 60
    property bool cfg_notificationsEnabledDefault: true
    property int cfg_panelWidthDefault: 112
    property bool cfg_showClaudeDefault: true
    property bool cfg_showCodexDefault: true
    property bool cfg_claudeUsageScraperDefault: false
    property string title: i18n("General")
    property bool claudeAvailable: true
    property bool codexAvailable: true
    property bool screenAvailable: false
    property string cliCheckCommand: "/bin/sh -c 'command -v claude >/dev/null && printf claude; command -v codex >/dev/null && printf \" codex\"; command -v screen >/dev/null && printf \" screen\"'"

    Plasma5Support.DataSource {
        id: cliCheck
        engine: "executable"
        onNewData: function(source, data) {
            if (source !== configPage.cliCheckCommand) return
            var commands = (data["stdout"] || "").trim().split(/\s+/)
            configPage.claudeAvailable = commands.indexOf("claude") !== -1
            configPage.codexAvailable = commands.indexOf("codex") !== -1
            configPage.screenAvailable = commands.indexOf("screen") !== -1
        }
    }
    Component.onCompleted: cliCheck.connectSource(cliCheckCommand)

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing

        Kirigami.Heading {
            text: i18n("General")
            level: 2
            Layout.fillWidth: true
            Layout.bottomMargin: Kirigami.Units.smallSpacing
        }

        Kirigami.FormLayout {
            Layout.fillWidth: true

            Controls.ComboBox {
                id: refresh
                property int value: 60
                Kirigami.FormData.label: i18n("Refresh Codex usage:")
                model: [i18n("Every minute"), i18n("Every 2 minutes"), i18n("Every 5 minutes"), i18n("Every 10 minutes")]
                currentIndex: [60, 120, 300, 600].indexOf(value)
                onActivated: value = [60, 120, 300, 600][currentIndex]
            }

            Controls.CheckBox {
                id: notifications
                Kirigami.FormData.label: i18n("Notifications:")
                text: i18n("Notify at 75% and 90% usage")
            }

            Controls.ComboBox {
                id: panelWidth
                property int value: 112
                Kirigami.FormData.label: i18n("Panel width:")
                model: [i18n("Compact (96 px)"), i18n("Standard (112 px)"), i18n("Wide (144 px)")]
                currentIndex: [96, 112, 144].indexOf(value)
                onActivated: value = [96, 112, 144][currentIndex]
            }

            Controls.CheckBox {
                id: showClaude
                Kirigami.FormData.label: i18n("Providers:")
                text: configPage.claudeAvailable ? i18n("Show Claude Code") : i18n("Claude Code CLI not found")
                enabled: configPage.claudeAvailable
            }

            Controls.CheckBox {
                id: showCodex
                text: configPage.codexAvailable ? i18n("Show OpenAI Codex") : i18n("Codex CLI not found")
                enabled: configPage.codexAvailable
            }

            Controls.CheckBox {
                id: claudeUsageScraper
                Kirigami.FormData.label: i18n("Claude data source:")
                text: configPage.screenAvailable ? i18n("Use accurate /usage scraper (slower)") : i18n("Accurate /usage scraper needs GNU screen")
                enabled: configPage.claudeAvailable && configPage.screenAvailable
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: i18n("Runs Claude Code's /usage panel in the background. Automatic updates use a five-minute cache; Refresh now always gets a new reading.")
            }
        }

        Item { Layout.fillHeight: true }
    }
}
