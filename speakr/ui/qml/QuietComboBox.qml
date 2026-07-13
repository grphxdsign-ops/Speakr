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
        color: control.enabled ? control.tokens.text : control.tokens.disabledText
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.body
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: PlainText {
        x: control.width - width - control.tokens.space12
        y: (control.height - height) / 2
        text: "⌄"
        color: control.enabled ? control.tokens.mutedText : control.tokens.disabledText
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.body
    }

    background: Rectangle {
        radius: control.tokens.radius
        color: control.down ? control.tokens.pressed
                            : (control.hovered ? control.tokens.hover : control.tokens.surface)
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? control.tokens.focus : control.tokens.border
    }

    delegate: ItemDelegate {
        id: option
        width: control.popup.width
        height: Math.max(control.tokens.controlHeight, implicitHeight)
        highlighted: control.highlightedIndex === index
        focusPolicy: Qt.StrongFocus
        Accessible.role: Accessible.ListItem
        Accessible.name: modelData

        contentItem: PlainText {
            text: modelData
            color: option.enabled ? control.tokens.text : control.tokens.disabledText
            font.family: control.tokens.fontFamily
            font.pixelSize: control.tokens.body
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        background: Rectangle {
            color: option.highlighted ? control.tokens.hover : control.tokens.surface
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
            radius: control.tokens.radius
            color: control.tokens.surface
            border.width: 1
            border.color: control.tokens.border
        }
    }
}
