pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

ComboBox {
    id: control

    required property var tokens
    property string accessibleName: "Choice"
    property string accessibleDescription: ""
    readonly property string selectedValueDescription: displayText.length === 0
                                                       ? ""
                                                       : qsTr("Selected: %1").arg(displayText)
    readonly property bool usesHighlightSurface: enabled && (down || hovered)
    readonly property color resolvedBackgroundColor: !enabled
                                                      ? tokens.contentSurface
                                                      : (down ? tokens.pressed
                                                              : (hovered ? tokens.hover
                                                                         : tokens.contentSurface))
    readonly property color resolvedBorderColor: tokens.highContrast
                                                  && usesHighlightSurface
                                                  ? tokens.accentText
                                                  : tokens.border

    implicitHeight: Math.max(tokens.controlHeight,
                             selectedLabel.implicitHeight
                             + topPadding + bottomPadding)
    implicitWidth: tokens.metric(190)
    leftPadding: tokens.space12
    rightPadding: indicator.width + tokens.space16
    topPadding: tokens.space8
    bottomPadding: tokens.space8
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    Accessible.role: Accessible.ComboBox
    Accessible.name: accessibleName
    Accessible.description: selectedValueDescription.length === 0
                            ? accessibleDescription
                            : (accessibleDescription.length > 0
                               ? accessibleDescription + " " + selectedValueDescription
                               : selectedValueDescription)

    contentItem: PlainText {
        id: selectedLabel
        objectName: "comboSelectedLabel"
        leftPadding: 0
        rightPadding: control.tokens.space8
        text: control.displayText
        color: !control.enabled ? control.tokens.disabledText
               : (control.tokens.highContrast && (control.down || control.hovered)
                  ? control.tokens.accentText : control.tokens.text)
        font.family: control.tokens.fontFamily
        font.pixelSize: control.tokens.body
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
        elide: Text.ElideNone
        Accessible.ignored: true
    }

    indicator: PlainText {
        objectName: "comboIndicator"
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
            objectName: "comboBackground"
            anchors.fill: parent
            radius: control.tokens.radiusControl
            color: control.resolvedBackgroundColor
            border.width: control.tokens.borderWidth
            border.color: control.resolvedBorderColor

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
        objectName: "comboOptionDelegate"
        required property int index
        required property var modelData
        width: control.popup.width
        height: Math.max(control.tokens.controlHeight,
                         optionLabel.implicitHeight
                         + topPadding + bottomPadding)
        leftPadding: control.tokens.space12
        rightPadding: control.tokens.space12
        topPadding: control.tokens.space8
        bottomPadding: control.tokens.space8
        highlighted: control.highlightedIndex === index
        focusPolicy: Qt.StrongFocus
        Accessible.role: Accessible.ListItem
        Accessible.name: modelData

        contentItem: PlainText {
            id: optionLabel
            objectName: "comboOptionLabel"
            text: option.modelData
            color: !option.enabled ? control.tokens.disabledText
                   : (control.tokens.highContrast && option.highlighted
                      ? control.tokens.accentText : control.tokens.text)
            font.family: control.tokens.fontFamily
            font.pixelSize: control.tokens.body
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            Accessible.ignored: true
        }

        background: Rectangle {
            color: option.highlighted ? control.tokens.hover : control.tokens.surface
            border.width: option.visualFocus ? control.tokens.focusWidth : 0
            border.color: control.tokens.highContrast && option.highlighted
                          ? control.tokens.accentText : control.tokens.focus
        }
    }

    popup: Popup {
        objectName: "comboPopup"
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
