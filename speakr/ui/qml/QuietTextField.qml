import QtQuick
import QtQuick.Controls

TextField {
    id: control

    required property var tokens
    property string accessibleName: placeholderText
    property string accessibleDescription: ""

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

    Accessible.role: Accessible.EditableText
    Accessible.name: accessibleName
    Accessible.description: accessibleDescription

    background: Item {
        Rectangle {
            anchors.fill: parent
            radius: control.tokens.radiusControl
            color: control.tokens.contentSurface
            border.width: control.tokens.borderWidth
            border.color: control.tokens.border
        }

        FocusRing {
            anchors.fill: parent
            tokens: control.tokens
            shown: control.activeFocus
            cornerRadius: control.tokens.radiusControl
        }
    }
}
