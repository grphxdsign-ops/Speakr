import QtQuick
import QtQuick.Controls

Switch {
    id: control

    required property var tokens
    property string accessibleName: text
    property string accessibleDescription: ""
    readonly property color resolvedTrackColor: {
        if (!enabled) return tokens.disabledControlSurface
        if (checked)
            return down ? tokens.accentPressedSurface
                 : (hovered ? tokens.accentHoverSurface : tokens.accent)
        if (down) return tokens.pressed
        if (hovered) return tokens.hover
        return tokens.surfaceRaised
    }
    readonly property color resolvedKnobColor: !enabled
                                                ? tokens.disabledControlText
                                                : ((checked
                                                    || (tokens.highContrast
                                                        && (hovered || down)))
                                                   ? tokens.accentText : tokens.text)

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
        objectName: "switchTrack"
        implicitWidth: control.tokens.metric(48)
        implicitHeight: control.tokens.metric(28)
        x: 0
        y: (control.height - height) / 2
        radius: height / 2
        color: control.resolvedTrackColor
        border.width: control.tokens.borderWidth
        border.color: control.checked || control.hovered || control.down
                      ? control.tokens.accent : control.tokens.border

        Behavior on color {
            ColorAnimation { duration: control.tokens.motionHover }
        }

        FocusRing {
            anchors.fill: parent
            tokens: control.tokens
            shown: control.visualFocus
            cornerRadius: track.radius
        }

        Rectangle {
            id: knob
            objectName: "switchKnob"
            width: parent.height - control.tokens.metric(6)
            height: width
            radius: width / 2
            y: control.tokens.metric(3)
            x: control.checked
               ? parent.width - width - control.tokens.metric(3)
               : control.tokens.metric(3)
            color: control.resolvedKnobColor

            Behavior on x {
                NumberAnimation {
                    duration: control.tokens.motionToggle
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
