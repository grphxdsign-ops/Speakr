import QtQuick
import QtQuick.Controls

Switch {
    id: control

    required property var tokens
    property string accessibleName: text
    property string accessibleDescription: ""

    text: checked ? qsTr("On") : qsTr("Off")
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitHeight: tokens.controlHeight
    implicitWidth: indicator.implicitWidth + tokens.space12 + label.implicitWidth
    spacing: tokens.space12

    Accessible.role: Accessible.CheckBox
    Accessible.name: accessibleName
    Accessible.description: accessibleDescription
    Accessible.checked: checked

    indicator: Rectangle {
        id: track
        implicitWidth: control.tokens.metric(48)
        implicitHeight: control.tokens.metric(28)
        x: 0
        y: (control.height - height) / 2
        radius: height / 2
        color: control.checked ? control.tokens.accent : control.tokens.surfaceRaised
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? control.tokens.focus
                                          : (control.checked ? control.tokens.accent : control.tokens.border)

        Rectangle {
            id: knob
            width: parent.height - control.tokens.metric(6)
            height: width
            radius: width / 2
            y: control.tokens.metric(3)
            x: control.checked
               ? parent.width - width - control.tokens.metric(3)
               : control.tokens.metric(3)
            color: control.checked ? control.tokens.accentText : control.tokens.text

            Behavior on x {
                NumberAnimation {
                    duration: control.tokens.reduceMotion ? 0 : 140
                    easing.type: Easing.OutQuint
                }
            }
        }
    }

    contentItem: PlainText {
        id: label
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        color: control.enabled ? control.tokens.text : control.tokens.disabledText
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.label
        font.weight: Font.Medium
        verticalAlignment: Text.AlignVCenter
    }
}
