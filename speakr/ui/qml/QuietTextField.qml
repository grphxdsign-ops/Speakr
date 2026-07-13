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

    background: Rectangle {
        radius: control.tokens.radius
        color: control.tokens.surface
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? control.tokens.focus : control.tokens.border
    }
}
