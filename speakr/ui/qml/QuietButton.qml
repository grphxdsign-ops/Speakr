import QtQuick
import QtQuick.Controls

Button {
    id: control

    required property var tokens
    property string kind: "secondary" // primary | secondary | quiet | danger
    property string accessibleDescription: ""
    readonly property color resolvedContentColor: {
        if (!enabled) return tokens.disabledText
        if (kind === "primary") return tokens.accentText
        if (kind === "danger")
            return down || hovered ? tokens.dangerStrongText : tokens.danger
        if (tokens.highContrast && (down || hovered)) return tokens.accentText
        return tokens.text
    }
    readonly property color resolvedBackgroundColor: {
        if (!enabled) return tokens.surfaceRaised
        if (kind === "primary")
            return down ? tokens.accentPressedSurface
                 : (hovered ? tokens.accentHoverSurface : tokens.accent)
        if (kind === "danger")
            return down ? tokens.dangerPressedSurface
                 : (hovered ? tokens.dangerHoverSurface : tokens.dangerSurface)
        if (down) return tokens.pressed
        if (hovered) return tokens.hover
        return kind === "quiet" ? "transparent" : tokens.contentSurface
    }

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
        objectName: "buttonLabel"
        text: control.text
        color: control.resolvedContentColor
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.label
        font.weight: control.kind === "primary" ? Font.DemiBold : Font.Medium
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Item {
        Rectangle {
            objectName: "buttonBackground"
            anchors.fill: parent
            radius: control.tokens.radiusControl
            color: control.resolvedBackgroundColor
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
