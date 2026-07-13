import QtQuick
import QtQuick.Layouts

GridLayout {
    id: root

    required property var tokens
    property string title: ""
    property string description: ""
    property string actionText: ""
    property string actionDescription: ""

    signal actionRequested()

    columns: width >= tokens.metric(480) ? 2 : 1
    columnSpacing: tokens.space16
    rowSpacing: tokens.space8
    Accessible.role: Accessible.Grouping
    Accessible.name: title
    Accessible.description: description

    ColumnLayout {
        Layout.fillWidth: true
        spacing: root.tokens.space4

        PlainText {
            Layout.fillWidth: true
            text: root.title
            color: root.tokens.text
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.sectionHeading
            font.weight: Font.DemiBold
            wrapMode: Text.Wrap
            Accessible.ignored: true
        }

        PlainText {
            Layout.fillWidth: true
            visible: root.description.length > 0
            text: root.description
            color: root.tokens.mutedText
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.secondary
            wrapMode: Text.Wrap
            Accessible.ignored: true
        }
    }

    QuietButton {
        visible: root.actionText.length > 0
        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
        tokens: root.tokens
        text: root.actionText
        kind: "quiet"
        accessibleDescription: root.actionDescription
        onClicked: root.actionRequested()
    }
}
