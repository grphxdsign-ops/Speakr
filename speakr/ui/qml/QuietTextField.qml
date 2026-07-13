import QtQuick
import QtQuick.Controls

TextField {
    id: control

    required property var tokens
    property string accessibleName: placeholderText
    property string accessibleDescription: ""
    property bool error: false
    property string errorMessage: ""
    readonly property color resolvedBackgroundColor: error ? tokens.dangerSurface
                                                            : (hovered && !tokens.highContrast
                                                               ? tokens.surfaceRaised
                                                               : tokens.contentSurface)
    readonly property color resolvedBorderColor: error ? tokens.danger
                                                        : (hovered && !tokens.highContrast
                                                           ? tokens.accent
                                                           : tokens.border)

    implicitHeight: tokens.controlHeight
    implicitWidth: tokens.metric(220)
    leftPadding: tokens.space12
    rightPadding: tokens.space12
    color: enabled ? tokens.text : tokens.disabledText
    placeholderTextColor: tokens.mutedText
    selectionColor: tokens.accent
    selectedTextColor: tokens.accentText
    font.family: tokens.fontFamily
    font.pixelSize: tokens.body
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true

    Accessible.role: Accessible.EditableText
    Accessible.name: accessibleName
    Accessible.description: error && errorMessage.length > 0
                            ? (accessibleDescription.length > 0
                               ? accessibleDescription + ". " + errorMessage
                               : errorMessage)
                            : accessibleDescription

    background: Item {
        Rectangle {
            objectName: "textFieldBackground"
            anchors.fill: parent
            radius: control.tokens.radiusControl
            color: control.resolvedBackgroundColor
            border.width: control.tokens.borderWidth
            border.color: control.resolvedBorderColor

            Behavior on color {
                ColorAnimation { duration: control.tokens.motionHover }
            }

            Behavior on border.color {
                ColorAnimation { duration: control.tokens.motionHover }
            }
        }

        FocusRing {
            anchors.fill: parent
            tokens: control.tokens
            shown: control.activeFocus
            cornerRadius: control.tokens.radiusControl
        }
    }
}
