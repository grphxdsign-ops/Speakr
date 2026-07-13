import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    objectName: "vocabularyPage"

    required property var tokens
    property var appState: ({})
    property var manualWords: []
    property var learnedWords: []
    property int tabIndex: 0
    property string pendingAction: ""
    property string pendingTarget: ""
    property string pendingId: ""

    function focusHeading() {
        pageHeading.forceActiveFocus(Qt.OtherFocusReason)
    }

    function field(item, key, fallbackValue) {
        if (item !== null && item !== undefined && typeof item === "object"
                && item[key] !== null && item[key] !== undefined)
            return item[key]
        return fallbackValue
    }

    function isReplacement(item) {
        if (typeof item !== "object" || item === null)
            return false
        return field(item, "kind", "") === "replacement"
                || (String(field(item, "heard", "")).length > 0
                    && String(field(item, "intended", "")).length > 0)
    }

    function manualList(replacements) {
        var result = []
        var source = manualWords || []
        for (var i = 0; i < source.length; ++i) {
            if (isReplacement(source[i]) === replacements)
                result.push(source[i])
        }
        return result
    }

    function wordText(item) {
        if (typeof item === "string") return item
        return String(field(item, "word", field(item, "text", "")))
    }

    function rowId(item) {
        if (typeof item === "string") return item
        return String(field(item, "id", field(item, "line", wordText(item))))
    }

    function requestDestructiveAction(action, target, idValue) {
        pendingAction = action
        pendingTarget = target
        pendingId = idValue
        confirmDialog.open()
    }

    function confirmDestructiveAction() {
        if (pendingAction === "manual")
            bridge.removeManualWord(pendingId)
        else if (pendingAction === "learned")
            bridge.forgetLearnedWord(pendingTarget)
        confirmDialog.close()
    }

    function issue() {
        return field(appState, "last_issue", null)
    }

    function issueCode() {
        return String(field(issue(), "code", ""))
    }

    function vocabularyIssueVisible() {
        return ["busy_setting", "dictionary_invalid", "dictionary_changed",
                "vocabulary_save_failed"].indexOf(issueCode()) >= 0
    }

    function issueActionLabel() {
        var action = String(field(issue(), "action", ""))
        if (action === "open_dictionary") return qsTr("Open local dictionary")
        if (action === "reload_dictionary") return qsTr("Reload Vocabulary")
        return qsTr("Dismiss")
    }

    function runIssueAction() {
        var action = String(field(issue(), "action", ""))
        if (action === "open_dictionary") bridge.openLocal("dictionary")
        else if (action === "reload_dictionary") bridge.reloadLocalState()
        else bridge.dismissIssue()
    }

    function submitWord() {
        var word = newWord.text.trim()
        if (word.length > 0 && bridge.addWord(word))
            newWord.clear()
    }

    function submitReplacement() {
        var heard = newHeard.text.trim()
        var intended = newIntended.text.trim()
        if (heard.length > 0 && intended.length > 0
                && bridge.addReplacement(heard, intended)) {
            newHeard.clear()
            newIntended.clear()
        }
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            spacing: root.tokens.space24

            Item { Layout.preferredHeight: root.tokens.space8 }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: root.tokens.space8

                PlainText {
                    id: pageHeading
                    Layout.fillWidth: true
                    text: qsTr("Vocabulary")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.pageHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                    Accessible.name: text
                }

                PlainText {
                    Layout.fillWidth: true
                    text: qsTr("Teach Speakr names, specialized words, and exact replacements. Everything stays local.")
                    color: root.tokens.mutedText
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    wrapMode: Text.Wrap
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                visible: root.vocabularyIssueVisible()
                implicitHeight: vocabularyIssueContent.implicitHeight + root.tokens.space24
                radius: root.tokens.radius
                color: root.issueCode() === "busy_setting"
                       ? root.tokens.warningSurface : root.tokens.dangerSurface
                border.width: 1
                border.color: root.issueCode() === "busy_setting"
                              ? root.tokens.warning : root.tokens.danger
                Accessible.role: Accessible.AlertMessage
                Accessible.name: String(root.field(root.issue(), "message", ""))

                GridLayout {
                    id: vocabularyIssueContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: root.tokens.space12
                    columns: width >= root.tokens.metric(520) ? 2 : 1
                    columnSpacing: root.tokens.space16
                    rowSpacing: root.tokens.space8

                    PlainText {
                        Layout.fillWidth: true
                        text: String(root.field(root.issue(), "message", ""))
                        color: root.issueCode() === "busy_setting"
                               ? root.tokens.warning : root.tokens.danger
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }

                    QuietButton {
                        tokens: root.tokens
                        text: root.issueActionLabel()
                        kind: root.issueCode() === "busy_setting" ? "secondary" : "primary"
                        accessibleDescription: qsTr("Perform the recommended Vocabulary recovery action")
                        onClicked: root.runIssueAction()
                    }
                }
            }

            Flow {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: root.tokens.space8
                Accessible.role: Accessible.PageTabList
                Accessible.name: qsTr("Vocabulary sections")

                NavigationButton {
                    tokens: root.tokens
                    text: qsTr("Manual words (%1)").arg(root.manualList(false).length)
                    selected: root.tabIndex === 0
                    Accessible.description: qsTr("Words you explicitly added")
                    onClicked: root.tabIndex = 0
                }

                NavigationButton {
                    tokens: root.tokens
                    text: qsTr("Replacements (%1)").arg(root.manualList(true).length)
                    selected: root.tabIndex === 1
                    Accessible.description: qsTr("Exact heard-to-intended phrase replacements")
                    onClicked: root.tabIndex = 1
                }

                NavigationButton {
                    tokens: root.tokens
                    text: qsTr("Learned words (%1)").arg((root.learnedWords || []).length)
                    selected: root.tabIndex === 2
                    Accessible.description: qsTr("Words learned from local dictation")
                    onClicked: root.tabIndex = 2
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                currentIndex: root.tabIndex

                ColumnLayout {
                    spacing: root.tokens.space16

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.tokens.space12

                        QuietTextField {
                            id: newWord
                            objectName: "newManualWordField"
                            Layout.fillWidth: true
                            tokens: root.tokens
                            placeholderText: qsTr("Add a name or specialized word")
                            accessibleName: qsTr("New manual word")
                            onAccepted: root.submitWord()
                        }

                        QuietButton {
                            id: addWord
                            tokens: root.tokens
                            text: qsTr("Add word")
                            kind: "primary"
                            enabled: newWord.text.trim().length > 0
                            onClicked: root.submitWord()
                        }
                    }

                    PlainText {
                        Layout.fillWidth: true
                        visible: root.manualList(false).length === 0
                        text: qsTr("No manual words yet. Add names or terms that speech models often miss.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                        Accessible.name: text
                    }

                    Repeater {
                        model: root.manualList(false)

                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: wordRow.implicitHeight + root.tokens.space16
                            radius: root.tokens.radius
                            color: "transparent"
                            border.width: 1
                            border.color: root.tokens.border

                            RowLayout {
                                id: wordRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: root.tokens.space8
                                spacing: root.tokens.space12

                                PlainText {
                                    Layout.fillWidth: true
                                    text: root.wordText(modelData)
                                    color: root.tokens.text
                                    font.family: root.tokens.fontFamily
                                    font.pixelSize: root.tokens.body
                                    font.weight: Font.Medium
                                    wrapMode: Text.Wrap
                                    Accessible.name: qsTr("Manual word: %1").arg(text)
                                }

                                QuietButton {
                                    tokens: root.tokens
                                    text: qsTr("Remove")
                                    kind: "danger"
                                    accessibleDescription: qsTr("Remove %1 from manual words").arg(root.wordText(modelData))
                                    onClicked: root.requestDestructiveAction("manual",
                                                                            root.wordText(modelData),
                                                                            root.rowId(modelData))
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    spacing: root.tokens.space16

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= root.tokens.metric(560) ? 3 : 1
                        columnSpacing: root.tokens.space12
                        rowSpacing: root.tokens.space8

                        QuietTextField {
                            id: newHeard
                            objectName: "newReplacementHeardField"
                            Layout.fillWidth: true
                            tokens: root.tokens
                            placeholderText: qsTr("What Speakr heard")
                            accessibleName: qsTr("Heard phrase")
                        }

                        QuietTextField {
                            id: newIntended
                            objectName: "newReplacementIntendedField"
                            Layout.fillWidth: true
                            tokens: root.tokens
                            placeholderText: qsTr("What you intended")
                            accessibleName: qsTr("Intended phrase")
                            onAccepted: root.submitReplacement()
                        }

                        QuietButton {
                            id: addReplacement
                            tokens: root.tokens
                            text: qsTr("Add replacement")
                            kind: "primary"
                            enabled: newHeard.text.trim().length > 0 && newIntended.text.trim().length > 0
                            onClicked: root.submitReplacement()
                        }
                    }

                    PlainText {
                        Layout.fillWidth: true
                        visible: root.manualList(true).length === 0
                        text: qsTr("No replacements yet. Add one when the same phrase needs the same correction every time.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                        Accessible.name: text
                    }

                    Repeater {
                        model: root.manualList(true)

                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: replacementRow.implicitHeight + root.tokens.space16
                            radius: root.tokens.radius
                            color: "transparent"
                            border.width: 1
                            border.color: root.tokens.border

                            RowLayout {
                                id: replacementRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: root.tokens.space8
                                spacing: root.tokens.space12

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: root.tokens.space4

                                    PlainText {
                                        Layout.fillWidth: true
                                        text: qsTr("Heard: %1").arg(String(root.field(modelData, "heard", "")))
                                        color: root.tokens.mutedText
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.secondary
                                        wrapMode: Text.Wrap
                                    }

                                    PlainText {
                                        Layout.fillWidth: true
                                        text: qsTr("Use: %1").arg(String(root.field(modelData, "intended", "")))
                                        color: root.tokens.text
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.body
                                        font.weight: Font.Medium
                                        wrapMode: Text.Wrap
                                        Accessible.name: text
                                    }
                                }

                                QuietButton {
                                    tokens: root.tokens
                                    text: qsTr("Remove")
                                    kind: "danger"
                                    accessibleDescription: qsTr("Remove this replacement")
                                    onClicked: root.requestDestructiveAction(
                                                   "manual",
                                                   qsTr("%1 → %2")
                                                   .arg(String(root.field(modelData, "heard", "")))
                                                   .arg(String(root.field(modelData, "intended", ""))),
                                                   root.rowId(modelData))
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    spacing: root.tokens.space16

                    PlainText {
                        Layout.fillWidth: true
                        text: qsTr("Learned words are stored only on this device. Approve useful words or forget ones you do not want suggested.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }

                    PlainText {
                        Layout.fillWidth: true
                        visible: (root.learnedWords || []).length === 0
                        text: qsTr("No learned words yet. Speakr will suggest recurring uncommon words here when local learning is on.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                        Accessible.name: text
                    }

                    Repeater {
                        model: root.learnedWords || []

                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: learnedRow.implicitHeight + root.tokens.space16
                            radius: root.tokens.radius
                            color: "transparent"
                            border.width: 1
                            border.color: root.tokens.border

                            GridLayout {
                                id: learnedRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: root.tokens.space8
                                columns: width >= root.tokens.metric(560) ? 2 : 1
                                columnSpacing: root.tokens.space16
                                rowSpacing: root.tokens.space8

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: root.tokens.space4

                                    PlainText {
                                        Layout.fillWidth: true
                                        text: root.wordText(modelData)
                                        color: root.tokens.text
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.body
                                        font.weight: Font.Medium
                                        wrapMode: Text.Wrap
                                        Accessible.name: qsTr("Learned word: %1").arg(text)
                                    }

                                    PlainText {
                                        Layout.fillWidth: true
                                        text: root.field(modelData, "last_seen", "").length > 0
                                              ? qsTr("Last seen %1").arg(root.field(modelData, "last_seen", ""))
                                              : qsTr("Seen %1 times").arg(root.field(modelData, "count", 1))
                                        color: root.tokens.mutedText
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.secondary
                                        wrapMode: Text.Wrap
                                    }
                                }

                                Flow {
                                    Layout.fillWidth: true
                                    spacing: root.tokens.space8

                                    QuietButton {
                                        tokens: root.tokens
                                        text: qsTr("Approve")
                                        enabled: !Boolean(root.field(modelData, "approved", false))
                                        accessibleDescription: qsTr("Approve %1 as a useful learned word").arg(root.wordText(modelData))
                                        onClicked: bridge.approveLearnedWord(root.wordText(modelData))
                                    }

                                    QuietButton {
                                        tokens: root.tokens
                                        text: qsTr("Forget")
                                        kind: "danger"
                                        accessibleDescription: qsTr("Forget %1 and remove its local learning entry").arg(root.wordText(modelData))
                                        onClicked: root.requestDestructiveAction("learned",
                                                                                root.wordText(modelData),
                                                                                root.wordText(modelData))
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                implicitHeight: fileRow.implicitHeight + root.tokens.space24
                radius: root.tokens.radius
                color: root.tokens.surfaceRaised
                border.width: 1
                border.color: root.tokens.border

                GridLayout {
                    id: fileRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: root.tokens.space12
                    columns: width >= root.tokens.metric(520) ? 2 : 1
                    columnSpacing: root.tokens.space16
                    rowSpacing: root.tokens.space8

                    PlainText {
                        Layout.fillWidth: true
                        text: qsTr("Expert option: edit the local dictionary file directly. Comments and ordering are preserved.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.secondary
                        wrapMode: Text.Wrap
                    }

                    QuietButton {
                        tokens: root.tokens
                        text: qsTr("Open dictionary file")
                        accessibleDescription: qsTr("Open the local plain-text vocabulary file")
                        onClicked: bridge.openLocal("dictionary")
                    }
                }
            }

            Item { Layout.preferredHeight: root.tokens.space24 }
        }
    }

    Dialog {
        id: confirmDialog
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(root.width - root.tokens.space32, root.tokens.metric(520))
        x: Math.max(root.tokens.space16, (root.width - width) / 2)
        y: Math.max(root.tokens.space16, (root.height - height) / 2)
        padding: root.tokens.space24
        onOpened: cancelRemoval.forceActiveFocus(Qt.TabFocusReason)
        onClosed: {
            root.pendingAction = ""
            root.pendingTarget = ""
            root.pendingId = ""
        }

        background: Rectangle {
            radius: root.tokens.radiusLarge
            color: root.tokens.surface
            border.width: 1
            border.color: root.tokens.border
        }

        contentItem: ColumnLayout {
            spacing: root.tokens.space16
            Accessible.role: Accessible.Dialog
            Accessible.name: root.pendingAction === "learned"
                             ? qsTr("Confirm forget learned word") : qsTr("Confirm remove vocabulary entry")
            Accessible.description: root.pendingTarget

            PlainText {
                Layout.fillWidth: true
                text: root.pendingAction === "learned" ? qsTr("Forget this learned word?")
                                                       : qsTr("Remove this vocabulary entry?")
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.sectionHeading
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
                Accessible.role: Accessible.Heading
            }

            PlainText {
                Layout.fillWidth: true
                text: root.pendingTarget
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.body
                font.weight: Font.Medium
                wrapMode: Text.Wrap
                Accessible.name: text
            }

            PlainText {
                Layout.fillWidth: true
                text: root.pendingAction === "learned"
                      ? qsTr("Speakr will remove its local learning entry.")
                      : qsTr("Speakr will remove it from the local dictionary file.")
                color: root.tokens.mutedText
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.body
                wrapMode: Text.Wrap
            }

            Flow {
                Layout.fillWidth: true
                spacing: root.tokens.space8

                QuietButton {
                    id: cancelRemoval
                    tokens: root.tokens
                    text: qsTr("Cancel")
                    kind: "primary"
                    accessibleDescription: qsTr("Keep this vocabulary entry")
                    onClicked: confirmDialog.close()
                }

                QuietButton {
                    tokens: root.tokens
                    text: root.pendingAction === "learned" ? qsTr("Forget") : qsTr("Remove")
                    kind: "danger"
                    accessibleDescription: root.pendingAction === "learned"
                                           ? qsTr("Forget the named learned word")
                                           : qsTr("Remove the named vocabulary entry")
                    onClicked: root.confirmDestructiveAction()
                }
            }
        }
    }
}
