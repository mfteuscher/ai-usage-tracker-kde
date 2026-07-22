import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Item {
    id: configPage
    implicitWidth: 380
    implicitHeight: content.implicitHeight + Kirigami.Units.largeSpacing * 2

    property alias cfg_refreshSeconds: refresh.value
    property alias cfg_notificationsEnabled: notifications.checked
    property int cfg_refreshSecondsDefault: 60
    property bool cfg_notificationsEnabledDefault: true
    property string title: i18n("General")

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
        }

        Item { Layout.fillHeight: true }
    }
}
