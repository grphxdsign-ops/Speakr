import QtQuick
import QtQuick.Controls

Button {
    id: control

    required property var tokens
    property string windowAction: "minimize" // minimize | maximize | restore | close
    property string accessibleDescription: ""
    readonly property string actionName: windowAction === "minimize" ? qsTr("Minimize")
                                         : (windowAction === "maximize" ? qsTr("Maximize")
                                            : (windowAction === "restore" ? qsTr("Restore")
                                                                   : qsTr("Close")))
    readonly property string glyph: windowAction === "minimize" ? "\u2212"
                                    : (windowAction === "maximize" ? "\u25a1"
                                       : (windowAction === "restore" ? "\u2750" : "\u00d7"))

    signal actionRequested(string action)

    implicitWidth: Math.max(44, tokens.controlHeight)
    implicitHeight: Math.max(44, tokens.controlHeight)
    leftPadding: 0
    rightPadding: 0
    topPadding: 0
    bottomPadding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    Accessible.role: Accessible.Button
    Accessible.name: actionName
    Accessible.description: accessibleDescription

    onClicked: actionRequested(windowAction)

    contentItem: PlainText {
        text: control.glyph
        color: !control.enabled ? control.tokens.disabledText
               : (control.tokens.highContrast && control.windowAction !== "close"
                  && (control.hovered || control.down)
                  ? control.tokens.accentText : control.tokens.text)
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.statusHeading
        font.weight: Font.Medium
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        Accessible.ignored: true
    }

    background: Item {
        Rectangle {
            anchors.fill: parent
            radius: control.tokens.radiusSmall
            color: {
                if (!control.enabled) return "transparent"
                if (control.windowAction === "close" && (control.hovered || control.down))
                    return control.tokens.dangerSurface
                if (control.down) return control.tokens.pressed
                if (control.hovered) return control.tokens.hover
                return "transparent"
            }
            border.width: control.windowAction === "close" && control.hovered ? 1 : 0
            border.color: control.tokens.danger

            Behavior on color {
                ColorAnimation { duration: control.tokens.motionHover }
            }
        }

        FocusRing {
            anchors.fill: parent
            tokens: control.tokens
            shown: control.visualFocus
            cornerRadius: control.tokens.radiusSmall
        }
    }
}
