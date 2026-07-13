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

    contentItem: PlainText {
        id: contentLabel
        text: control.text
        color: !control.enabled
               ? control.tokens.disabledText
               : (control.tokens.highContrast
                  && (control.down || control.hovered)
                  ? control.tokens.accentText
                  : (control.kind === "primary" ? control.tokens.accentText
                                                 : (control.kind === "danger"
                                                    ? control.tokens.danger
                                                    : control.tokens.text)))
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.label
        font.weight: control.kind === "primary" ? Font.DemiBold : Font.Medium
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Item {
        Rectangle {
            anchors.fill: parent
            radius: control.tokens.radiusControl
            color: {
                if (!control.enabled)
                    return control.tokens.surfaceRaised
                if (control.kind === "primary")
                    return control.down ? Qt.darker(control.tokens.accent, 1.10)
                                        : control.tokens.accent
                if (control.kind === "danger")
                    return control.down ? control.tokens.pressed
                                        : control.tokens.dangerSurface
                if (control.down)
                    return control.tokens.pressed
                if (control.hovered)
                    return control.tokens.hover
                return control.kind === "quiet" ? "transparent"
                                                : control.tokens.contentSurface
            }
            border.width: control.kind === "quiet" && !control.hovered
                          ? 0 : control.tokens.borderWidth
            border.color: control.kind === "danger" ? control.tokens.danger
                                                     : control.tokens.border

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
