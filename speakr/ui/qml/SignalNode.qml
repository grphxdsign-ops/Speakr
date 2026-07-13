import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root

    required property var tokens
    property string label: ""
    property bool reached: false
    property bool active: false
    property string accessibleDescription: ""

    spacing: tokens.space4
    Accessible.role: Accessible.StaticText
    Accessible.name: label + (active ? qsTr(", current stage")
                                    : (reached ? qsTr(", complete") : ""))
    Accessible.description: accessibleDescription

    Rectangle {
        objectName: "signalNodeSurface"
        readonly property color edgeColor: root.reached
                                            ? (root.tokens.highContrast
                                               ? root.tokens.accentText
                                               : root.tokens.accent)
                                            : (root.active
                                               && !root.tokens.highContrast
                                               ? root.tokens.accent
                                               : root.tokens.border)
        Layout.alignment: Qt.AlignHCenter
        implicitWidth: root.tokens.metric(24)
        implicitHeight: implicitWidth
        Layout.preferredWidth: implicitWidth
        Layout.preferredHeight: implicitHeight
        radius: implicitWidth / 2
        color: root.reached ? root.tokens.accent : root.tokens.surface
        border.width: root.active ? 2 : root.tokens.borderWidth
        border.color: edgeColor

        PlainText {
            objectName: "signalNodeGlyph"
            anchors.centerIn: parent
            text: root.reached ? "\u2713" : (root.active ? "\u2022" : "")
            color: root.reached ? root.tokens.accentText
                                : (root.tokens.highContrast
                                   ? root.tokens.text : root.tokens.accent)
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.body
            font.weight: Font.Bold
            Accessible.ignored: true
        }

        Behavior on color {
            ColorAnimation { duration: root.tokens.motionStage }
        }
    }

    PlainText {
        Layout.alignment: Qt.AlignHCenter
        Layout.fillWidth: true
        text: root.label
        color: root.active || root.reached ? root.tokens.text : root.tokens.mutedText
        font.family: root.tokens.fontFamily
        font.pixelSize: root.tokens.secondary
        font.weight: root.active ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        Accessible.ignored: true
    }
}
