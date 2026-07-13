import QtQuick
import QtQuick.Controls

Button {
    id: control

    required property var tokens
    property string kind: "secondary" // primary | secondary | quiet | danger
    property string accessibleDescription: ""

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitHeight: tokens.controlHeight
    implicitWidth: Math.max(tokens.controlHeight,
                            contentLabel.implicitWidth + tokens.space32)
    leftPadding: tokens.space16
    rightPadding: tokens.space16
    topPadding: tokens.space8
    bottomPadding: tokens.space8

    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.description: accessibleDescription

    contentItem: Text {
        id: contentLabel
        text: control.text
        color: !control.enabled
               ? control.tokens.disabledText
               : (control.kind === "primary" ? control.tokens.accentText
                                               : (control.kind === "danger" ? control.tokens.danger
                                                                             : control.tokens.text))
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.label
        font.weight: control.kind === "primary" ? Font.DemiBold : Font.Medium
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: control.tokens.radius
        color: {
            if (!control.enabled)
                return control.tokens.surfaceRaised
            if (control.kind === "primary")
                return control.down ? Qt.darker(control.tokens.accent, 1.12) : control.tokens.accent
            if (control.kind === "danger")
                return control.down ? control.tokens.pressed : control.tokens.dangerSurface
            if (control.down)
                return control.tokens.pressed
            if (control.hovered || control.visualFocus)
                return control.tokens.hover
            return control.kind === "quiet" ? "transparent" : control.tokens.surface
        }
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus
                      ? control.tokens.focus
                      : (control.kind === "danger" ? control.tokens.danger : control.tokens.border)

        Behavior on color {
            ColorAnimation { duration: control.tokens.motionFast }
        }
    }
}
