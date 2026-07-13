import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    required property var tokens
    property string candidate: ""
    readonly property bool risky: isOrdinaryKey(candidate)

    visible: risky
    implicitHeight: warningRow.implicitHeight + tokens.space16
    radius: tokens.radius
    color: tokens.warningSurface
    border.width: 1
    border.color: tokens.warning
    Accessible.role: Accessible.AlertMessage
    Accessible.name: qsTr("Shortcut conflict warning")
    Accessible.description: warningText.text

    function isOrdinaryKey(value) {
        var normalized = String(value).trim().toLowerCase()
        if (normalized.length === 0 || normalized.indexOf("+") >= 0)
            return false
        if (/^[a-z0-9]$/.test(normalized))
            return true
        var ordinary = [
            "space", "spacebar", "tab", "enter", "return", "backspace",
            "delete", "escape", "esc", "left", "right", "up", "down",
            "home", "end", "page up", "page down", "insert"
        ]
        return ordinary.indexOf(normalized) >= 0
    }

    RowLayout {
        id: warningRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: root.tokens.space8
        spacing: root.tokens.space8

        PlainText {
            text: "!"
            color: root.tokens.warning
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.body
            font.weight: Font.Bold
            Accessible.ignored: true
        }

        PlainText {
            id: warningText
            Layout.fillWidth: true
            text: qsTr("This is an ordinary typing or navigation key. Speakr may start while you use it in another app. Confirm only if that is intentional.")
            color: root.tokens.text
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.secondary
            wrapMode: Text.Wrap
        }
    }
}
