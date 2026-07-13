import QtQuick
import QtQuick.Controls

QuietButton {
    id: control

    property bool selected: false

    kind: "quiet"
    Accessible.role: Accessible.PageTab
    Accessible.selected: selected

    contentItem: PlainText {
        text: control.text
        color: control.enabled ? control.tokens.text : control.tokens.disabledText
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.label
        font.weight: control.selected ? Font.DemiBold : Font.Medium
        horizontalAlignment: Text.AlignLeft
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: control.tokens.radius
        color: control.selected
               ? control.tokens.hover
               : (control.down ? control.tokens.pressed
                               : (control.hovered || control.visualFocus ? control.tokens.surfaceRaised
                                                                         : "transparent"))
        border.width: control.visualFocus ? 2 : (control.selected ? 1 : 0)
        border.color: control.visualFocus ? control.tokens.focus : control.tokens.border
    }
}
