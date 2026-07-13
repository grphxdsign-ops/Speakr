import QtQuick

Item {
    id: root

    required property var tokens
    property bool shown: false
    property int cornerRadius: tokens.radiusControl

    visible: shown
    enabled: false
    Accessible.ignored: true

    Rectangle {
        anchors.fill: parent
        anchors.margins: -(root.tokens.focusWidth + root.tokens.focusClearance)
        radius: root.cornerRadius + root.tokens.focusWidth + root.tokens.focusClearance
        color: "transparent"
        border.width: root.tokens.focusWidth
        border.color: root.tokens.focus
    }
}
