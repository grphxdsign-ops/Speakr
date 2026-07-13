pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

ComboBox {
    id: control

    required property var tokens
    property string accessibleName: "Choice"
    property string accessibleDescription: ""

    implicitHeight: tokens.controlHeight
    implicitWidth: tokens.metric(190)
    leftPadding: tokens.space12
    rightPadding: indicator.width + tokens.space16
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    Accessible.role: Accessible.ComboBox
    Accessible.name: accessibleName
    Accessible.description: accessibleDescription

    contentItem: PlainText {
        leftPadding: 0
        rightPadding: control.tokens.space8
        text: control.displayText
        color: !control.enabled ? control.tokens.disabledText
               : (control.tokens.highContrast && (control.down || control.hovered)
                  ? control.tokens.accentText : control.tokens.text)
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.body
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: PlainText {
        x: control.width - width - control.tokens.space12
        y: (control.height - height) / 2
        text: "\u2304"
        color: !control.enabled ? control.tokens.disabledText
               : (control.tokens.highContrast && (control.down || control.hovered)
                  ? control.tokens.accentText : control.tokens.mutedText)
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.body
        Accessible.ignored: true
    }

    background: Item {
        Rectangle {
            anchors.fill: parent
            radius: control.tokens.radiusControl
            color: control.down ? control.tokens.pressed
                                : (control.hovered ? control.tokens.hover
                                                   : control.tokens.contentSurface)
            border.width: control.tokens.borderWidth
            border.color: control.tokens.border

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

    delegate: ItemDelegate {
        id: option
        required property int index
        required property var modelData
        width: control.popup.width
        height: Math.max(control.tokens.controlHeight, implicitHeight)
        highlighted: control.highlightedIndex === index
        focusPolicy: Qt.StrongFocus
        Accessible.role: Accessible.ListItem
        Accessible.name: modelData

        contentItem: PlainText {
            text: option.modelData
            color: !option.enabled ? control.tokens.disabledText
                   : (control.tokens.highContrast && option.highlighted
                      ? control.tokens.accentText : control.tokens.text)
            font.family: control.tokens.fontFamily
            font.pixelSize: control.tokens.body
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        background: Rectangle {
            color: option.highlighted ? control.tokens.hover : control.tokens.surface
            border.width: option.visualFocus ? control.tokens.focusWidth : 0
            border.color: control.tokens.focus
        }
    }

    popup: Popup {
        y: control.height + control.tokens.space4
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + padding * 2,
                                 control.tokens.metric(320))
        padding: 1

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }

        background: Rectangle {
            radius: control.tokens.radiusControl
            color: control.tokens.surface
            border.width: control.tokens.borderWidth
            border.color: control.tokens.border
        }
    }
}
