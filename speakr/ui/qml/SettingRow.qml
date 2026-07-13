import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    required property var tokens
    property string label: ""
    property string description: ""
    property string category: ""
    property string path: ""
    property string controlType: "switch"
    property var options: []
    property var values: []
    property var currentValue
    property bool showCategory: false
    property bool capturingHotkey: false
    property string pendingHotkey: ""
    property string actionText: qsTr("Open")
    property string actionKind: "config"
    property bool allowEmpty: false
    property bool controlEnabled: true
    property string saveState: "" // "saved", "saving", "error", or empty
    property string validationMessage: ""

    signal changeRequested(string path, var value, var previousValue)
    signal actionRequested(string kind)

    color: "transparent"
    implicitHeight: rowLayout.implicitHeight + tokens.space24
    Accessible.role: Accessible.Grouping
    Accessible.name: label
    Accessible.description: description

    function sameValue(left, right) {
        if (left === null || left === undefined)
            return right === null || right === undefined
        if (right === null || right === undefined)
            return false
        return String(left) === String(right)
    }

    function valueIndex(value) {
        var source = values && values.length > 0 ? values : options
        for (var i = 0; i < source.length; ++i) {
            if (sameValue(source[i], value)) return i
        }
        return 0
    }

    function valueAt(index) {
        var source = values && values.length > 0 ? values : options
        return index >= 0 && index < source.length ? source[index] : currentValue
    }

    function displayCurrent() {
        if (currentValue instanceof Array)
            return currentValue.join(", ")
        if (currentValue === null || currentValue === undefined)
            return ""
        return String(currentValue)
    }

    Rectangle {
        objectName: "settingSeparator"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 1
        color: root.tokens.border
    }

    GridLayout {
        id: rowLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        columns: width >= root.tokens.metric(620) ? 2 : 1
        columnSpacing: root.tokens.space24
        rowSpacing: root.tokens.space12

        ColumnLayout {
            Layout.fillWidth: true
            spacing: root.tokens.space4

            PlainText {
                objectName: "settingCategoryLabel"
                Layout.fillWidth: true
                visible: root.showCategory
                text: root.category
                color: root.tokens.accentForeground
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.secondary
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
            }

            PlainText {
                Layout.fillWidth: true
                text: root.label
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.body
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
            }

            PlainText {
                Layout.fillWidth: true
                text: root.description
                color: root.tokens.mutedText
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.secondary
                wrapMode: Text.Wrap
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: root.tokens.space8

            QuietSwitch {
                visible: root.controlType === "switch"
                tokens: root.tokens
                checked: Boolean(root.currentValue)
                accessibleName: root.label
                accessibleDescription: root.description
                onToggled: {
                    root.changeRequested(root.path, checked, root.currentValue)
                    checked = Qt.binding(function() { return Boolean(root.currentValue) })
                }
            }

            QuietComboBox {
                id: immediateCombo
                visible: root.controlType === "combo"
                enabled: root.controlEnabled
                tokens: root.tokens
                model: root.options
                currentIndex: root.valueIndex(root.currentValue)
                accessibleName: root.label
                accessibleDescription: root.description
                onActivated: root.changeRequested(root.path, root.valueAt(currentIndex), root.currentValue)
            }

            QuietComboBox {
                id: confirmCombo
                property bool dirty: false
                property int pendingIndex: root.valueIndex(root.currentValue)

                visible: root.controlType === "confirm_combo"
                tokens: root.tokens
                model: root.options
                currentIndex: pendingIndex
                accessibleName: root.label
                accessibleDescription: qsTr("Choose a value, then select Apply")
                onActivated: {
                    pendingIndex = currentIndex
                    dirty = !root.sameValue(root.valueAt(currentIndex), root.currentValue)
                }

                Connections {
                    target: root
                    function onCurrentValueChanged() {
                        if (root.sameValue(root.valueAt(confirmCombo.pendingIndex),
                                           root.currentValue)) {
                            confirmCombo.dirty = false
                        } else if (!confirmCombo.dirty) {
                            confirmCombo.pendingIndex = root.valueIndex(root.currentValue)
                        }
                    }
                }
            }

            QuietButton {
                visible: root.controlType === "confirm_combo"
                tokens: root.tokens
                text: qsTr("Apply")
                kind: "primary"
                enabled: confirmCombo.dirty
                accessibleDescription: qsTr("Apply the selected %1 setting").arg(root.label)
                onClicked: {
                    root.changeRequested(root.path, root.valueAt(confirmCombo.pendingIndex), root.currentValue)
                }
            }

            QuietTextField {
                id: textInput
                visible: root.controlType === "text" || root.controlType === "number"
                tokens: root.tokens
                text: root.displayCurrent()
                inputMethodHints: root.controlType === "number" ? Qt.ImhFormattedNumbersOnly : Qt.ImhNone
                accessibleName: root.label
                accessibleDescription: root.description
                onEditingFinished: {
                    var nextValue = root.controlType === "number" ? Number(text) : text
                    if (!root.sameValue(nextValue, root.currentValue)
                            && (text.trim().length > 0
                                || (root.controlType === "text" && root.allowEmpty)))
                        root.changeRequested(root.path, nextValue, root.currentValue)
                }
            }

            ColumnLayout {
                visible: root.controlType === "hotkey"
                spacing: root.tokens.space8

                PlainText {
                        text: root.capturingHotkey
                          ? (root.pendingHotkey.length > 0
                             ? qsTr("Captured: %1").arg(root.pendingHotkey)
                             : qsTr("Press one key"))
                          : String(root.currentValue)
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    font.weight: Font.Medium
                    wrapMode: Text.Wrap
                    Accessible.name: text
                }

                Flow {
                    spacing: root.tokens.space8

                    QuietButton {
                        tokens: root.tokens
                        text: root.capturingHotkey ? qsTr("Cancel") : qsTr("Change shortcut")
                        kind: root.capturingHotkey ? "danger" : "secondary"
                        accessibleDescription: root.capturingHotkey
                                               ? qsTr("Cancel shortcut capture. Escape also cancels.")
                                               : qsTr("Wait for one key with no time limit. Cancel or Escape stops capture.")
                        onClicked: root.capturingHotkey
                                   ? bridge.cancelHotkeyCapture() : bridge.beginHotkeyCapture()
                    }

                    QuietButton {
                        visible: root.capturingHotkey && root.pendingHotkey.length > 0
                        tokens: root.tokens
                        text: qsTr("Use shortcut")
                        kind: "primary"
                        accessibleDescription: qsTr("Confirm %1 as the dictation shortcut").arg(root.pendingHotkey)
                        onClicked: bridge.confirmHotkey()
                    }
                }

                HotkeyWarning {
                    Layout.fillWidth: true
                    tokens: root.tokens
                    candidate: root.pendingHotkey
                }
            }

            QuietButton {
                visible: root.controlType === "action"
                tokens: root.tokens
                text: root.actionText
                accessibleDescription: root.description
                onClicked: root.actionRequested(root.actionKind)
            }
        }

        PlainText {
            Layout.fillWidth: true
            Layout.columnSpan: rowLayout.columns
            visible: root.validationMessage.length > 0 || root.saveState.length > 0
            text: root.validationMessage.length > 0
                  ? root.validationMessage
                  : (root.saveState === "saved" ? qsTr("Saved")
                     : (root.saveState === "saving" ? qsTr("Saving")
                        : (root.saveState === "error" ? qsTr("Could not save") : "")))
            color: root.validationMessage.length > 0 || root.saveState === "error"
                   ? root.tokens.danger
                   : (root.saveState === "saved" ? root.tokens.success
                                                  : root.tokens.mutedText)
            font.family: root.tokens.fontFamily
            font.pixelSize: root.tokens.secondary
            font.weight: Font.DemiBold
            wrapMode: Text.Wrap
            Accessible.role: root.validationMessage.length > 0 || root.saveState === "error"
                             ? Accessible.AlertMessage : Accessible.StaticText
        }
    }
}
