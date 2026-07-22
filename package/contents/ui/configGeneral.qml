import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.plasma.configuration

ConfigPage {
    property alias cfg_refreshSeconds: refresh.currentValue
    property alias cfg_notificationsEnabled: notifications.checked

    ColumnLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        Controls.Label { text: i18n("Refresh Codex usage") }
        Controls.ComboBox {
            id: refresh
            property int currentValue: [60, 120, 300, 600][currentIndex]
            model: [i18n("Every minute"), i18n("Every 2 minutes"), i18n("Every 5 minutes"), i18n("Every 10 minutes")]
            Component.onCompleted: currentIndex = [60, 120, 300, 600].indexOf(currentValue)
        }
        Controls.CheckBox {
            id: notifications
            text: i18n("Notify at 75% and 90% usage")
        }
    }
}
