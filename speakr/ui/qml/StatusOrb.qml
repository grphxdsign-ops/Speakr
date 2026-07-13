import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root

    required property var tokens
    property string statusKind: "neutral" // neutral | active | success | warning | danger
    property string symbol: statusKind === "success" ? "\u2713"
                            : (statusKind === "warning" ? "!"
                               : (statusKind === "danger" ? "\u00d7" : "\u2022"))
    property string label: ""
    property string description: ""
    property bool compact: false
    readonly property color stateColor: statusKind === "success" ? tokens.success
                                        : (statusKind === "warning" ? tokens.warning
                                           : (statusKind === "danger" ? tokens.danger
                                              : (statusKind === "active" ? tokens.accent
                                                                     : tokens.border)))

    spacing: tokens.space8
    implicitHeight: Math.max(tokens.metric(compact ? 28 : 36), labelText.implicitHeight)
    Accessible.role: Accessible.StaticText
    Accessible.name: label
    Accessible.description: description.length > 0 ? description : statusKind

    Rectangle {
        objectName: "statusOrbBadge"
        readonly property color edgeColor: root.tokens.highContrast
                                              ? root.tokens.accentText
                                              : root.stateColor
        Layout.preferredWidth: root.tokens.metric(root.compact ? 24 : 30)
        Layout.preferredHeight: Layout.preferredWidth
        Layout.alignment: Qt.AlignVCenter
        radius: width / 2
        color: root.tokens.highContrast
               ? root.tokens.accent
               : root.tokens.withAlpha(root.stateColor, 0.16)
        border.width: root.tokens.highContrast ? 2 : 1
        border.color: edgeColor

        PlainText {
            objectName: "statusOrbGlyph"
            anchors.centerIn: parent
            text: root.symbol
            color: root.tokens.highContrast ? root.tokens.accentText : root.stateColor
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.fontSize(root.compact ? 14 : 16)
            font.weight: Font.Bold
            Accessible.ignored: true
        }
    }

    PlainText {
        id: labelText
        Layout.fillWidth: true
        text: root.label
        color: root.tokens.text
        font.family: root.tokens.fontFamily
        font.pixelSize: root.tokens.body
        font.weight: Font.DemiBold
        wrapMode: Text.Wrap
        verticalAlignment: Text.AlignVCenter
        Accessible.ignored: true
    }
}
