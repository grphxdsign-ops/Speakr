import QtQuick
import QtQuick.Layouts

QuietButton {
    id: control

    property bool selected: false

    kind: "quiet"
    implicitHeight: Math.max(tokens.controlHeight, navLabel.implicitHeight + tokens.space16)
    Accessible.role: Accessible.PageTab
    Accessible.selected: selected

    contentItem: RowLayout {
        spacing: control.tokens.space8

        Rectangle {
            objectName: "navigationSelectionMarker"
            Layout.preferredWidth: control.tokens.metric(8)
            Layout.preferredHeight: Layout.preferredWidth
            Layout.alignment: Qt.AlignVCenter
            radius: width / 2
            visible: control.selected
            color: control.tokens.highContrast ? control.tokens.accentText
                                               : control.tokens.accent
            Accessible.ignored: true
        }

        PlainText {
            id: navLabel
            Layout.fillWidth: true
            text: control.text
            color: control.tokens.highContrast && control.selected
                   ? control.tokens.accentText
                   : (!control.enabled
                      ? control.tokens.disabledText
                      : (control.tokens.highContrast
                         && (control.hovered || control.down)
                         ? control.tokens.accentText : control.tokens.text))
            font.family: control.tokens.fontFamily
            font.pixelSize: control.tokens.label
            font.weight: control.selected ? Font.DemiBold : Font.Medium
            horizontalAlignment: Text.AlignLeft
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.Wrap
            Accessible.ignored: true
        }
    }

    background: Item {
        Rectangle {
            objectName: "navigationBackground"
            readonly property color edgeColor:
                control.selected
                ? (control.tokens.highContrast
                   ? control.tokens.accentText : control.tokens.accent)
                : control.tokens.border
            anchors.fill: parent
            radius: control.tokens.radiusControl
            color: control.selected
                   ? (control.tokens.highContrast ? control.tokens.accent
                                                  : control.tokens.hover)
                   : (control.down ? control.tokens.pressed
                                   : (control.hovered ? control.tokens.hover
                                                      : "transparent"))
            border.width: control.selected ? control.tokens.borderWidth : 0
            border.color: edgeColor

            Behavior on color {
                ColorAnimation { duration: control.tokens.motionHover }
            }
        }

        FocusRing {
            anchors.fill: parent
            tokens: control.tokens
            shown: control.visualFocus
            cornerRadius: control.tokens.radiusControl
        }
    }
}
