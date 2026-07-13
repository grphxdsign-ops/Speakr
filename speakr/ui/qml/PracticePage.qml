import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    objectName: "practicePage"

    required property var tokens
    property var practice: ({})
    property var appState: ({})
    signal navigateRequested(string page)

    function focusHeading() {
        pageHeading.forceActiveFocus(Qt.OtherFocusReason)
    }

    function value(source, key, fallbackValue) {
        if (source !== null && source !== undefined
                && source[key] !== null && source[key] !== undefined)
            return source[key]
        return fallbackValue
    }

    function levelCount() {
        var level = String(value(practice, "mic_level_band", value(appState, "mic_level_band", "silent")))
        if (level === "high") return 5
        if (level === "good") return 4
        if (level === "low") return 2
        return 0
    }

    function levelLabel() {
        var level = String(value(practice, "mic_level_band", value(appState, "mic_level_band", "silent")))
        if (level === "high") return qsTr("High")
        if (level === "good") return qsTr("Good")
        if (level === "low") return qsTr("Low")
        return qsTr("Waiting for sound")
    }

    function heardText() {
        return String(value(practice, "heard", value(practice, "text", "")))
    }

    function wouldTypeText() {
        return String(value(practice, "would_type",
                            value(practice, "wouldType", value(practice, "text", ""))))
    }

    function vocabularyIssue() {
        return value(appState, "last_issue", null)
    }

    function vocabularyIssueCode() {
        var issue = vocabularyIssue()
        return issue && issue.code !== undefined ? String(issue.code) : ""
    }

    function vocabularyIssueVisible() {
        return ["busy_setting", "dictionary_invalid", "dictionary_changed",
                "vocabulary_save_failed"].indexOf(vocabularyIssueCode()) >= 0
    }

    function submitWord() {
        var word = wordField.text.trim()
        if (word.length > 0 && bridge.addWord(word))
            wordField.clear()
    }

    function submitReplacement() {
        var heard = heardField.text.trim()
        var intended = intendedField.text.trim()
        if (heard.length > 0 && intended.length > 0
                && bridge.addReplacement(heard, intended)) {
            heardField.clear()
            intendedField.clear()
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
                    text: qsTr("Practice")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.pageHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                    Accessible.name: text
                }

                PlainText {
                    Layout.fillWidth: true
                    text: qsTr("Try a dictation without inserting text anywhere.")
                    color: root.tokens.mutedText
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    wrapMode: Text.Wrap
                }

                PlainText {
                    Layout.fillWidth: true
                    text: qsTr("Not stored by Speakr; clears when you leave Practice.")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                    Accessible.name: text
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                implicitHeight: practiceContent.implicitHeight + root.tokens.space32
                radius: root.tokens.radiusLarge
                color: root.tokens.surface
                border.width: 1
                border.color: root.tokens.border

                ColumnLayout {
                    id: practiceContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: root.tokens.space16
                    spacing: root.tokens.space16

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.tokens.space16

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: root.tokens.space8

                            PlainText {
                                text: root.value(root.practice, "active", false)
                                      ? qsTr("Listening")
                                      : (root.value(root.practice, "busy", false)
                                         ? qsTr("Transcribing locally") : qsTr("Ready to practice"))
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.statusHeading
                                font.weight: Font.DemiBold
                                Accessible.role: Accessible.Heading
                                Accessible.name: text
                            }

                            RowLayout {
                                spacing: root.tokens.space8
                                Accessible.role: Accessible.ProgressBar
                                Accessible.name: qsTr("Microphone input level: %1").arg(root.levelLabel())

                                Repeater {
                                    model: 5
                                    Rectangle {
                                        required property int index
                                        width: root.tokens.metric(28)
                                        height: root.tokens.metric(10)
                                        radius: height / 2
                                        color: index < root.levelCount() ? root.tokens.accent : root.tokens.surfaceRaised
                                        border.width: 1
                                        border.color: index < root.levelCount() ? root.tokens.accent : root.tokens.border

                                        Behavior on color {
                                            ColorAnimation { duration: root.tokens.motionFast }
                                        }
                                    }
                                }

                                PlainText {
                                    text: root.levelLabel()
                                    color: root.tokens.mutedText
                                    font.family: root.tokens.fontFamily
                                    font.pixelSize: root.tokens.secondary
                                }
                            }
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: root.value(root.practice, "active", false) ? qsTr("Stop") : qsTr("Start")
                            kind: root.value(root.practice, "active", false) ? "secondary" : "primary"
                            enabled: root.value(root.practice, "active", false)
                                     || !root.value(root.practice, "busy", false)
                            accessibleDescription: root.value(root.practice, "active", false)
                                                   ? qsTr("Stop this temporary practice recording")
                                                   : qsTr("Start a temporary practice recording")
                            onClicked: root.value(root.practice, "active", false)
                                       ? bridge.stopPractice() : bridge.startPractice()
                        }
                    }

                    PlainText {
                        Layout.fillWidth: true
                        visible: root.value(root.practice, "error", "").length > 0
                        text: root.value(root.practice, "error", "")
                        color: root.tokens.danger
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                        Accessible.role: Accessible.AlertMessage
                        Accessible.name: text
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= root.tokens.metric(620) ? 2 : 1
                        columnSpacing: root.tokens.space16
                        rowSpacing: root.tokens.space16

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: root.tokens.space8

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("What Speakr heard")
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                                Accessible.role: Accessible.Heading
                            }

                            PlainTextArea {
                                id: heardTranscript
                                Layout.fillWidth: true
                                Layout.minimumHeight: root.tokens.metric(150)
                                readOnly: true
                                text: root.heardText()
                                placeholderText: qsTr("Recognized speech will appear here.")
                                wrapMode: TextEdit.Wrap
                                color: root.tokens.text
                                placeholderTextColor: root.tokens.mutedText
                                selectionColor: root.tokens.accent
                                selectedTextColor: root.tokens.accentText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                leftPadding: root.tokens.space16
                                rightPadding: root.tokens.space16
                                topPadding: root.tokens.space16
                                bottomPadding: root.tokens.space16
                                Accessible.role: Accessible.EditableText
                                Accessible.name: qsTr("What Speakr heard")
                                Accessible.description: qsTr("Read only. This text is held in memory and clears when Practice closes.")

                                background: Rectangle {
                                    radius: root.tokens.radius
                                    color: root.tokens.background
                                    border.width: heardTranscript.activeFocus ? 2 : 1
                                    border.color: heardTranscript.activeFocus ? root.tokens.focus : root.tokens.border
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: root.tokens.space8

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("What Speakr would type")
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                                Accessible.role: Accessible.Heading
                            }

                            PlainTextArea {
                                id: wouldTypeTranscript
                                Layout.fillWidth: true
                                Layout.minimumHeight: root.tokens.metric(150)
                                readOnly: true
                                text: root.wouldTypeText()
                                placeholderText: qsTr("Locally cleaned-up text will appear here.")
                                wrapMode: TextEdit.Wrap
                                color: root.tokens.text
                                placeholderTextColor: root.tokens.mutedText
                                selectionColor: root.tokens.accent
                                selectedTextColor: root.tokens.accentText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                leftPadding: root.tokens.space16
                                rightPadding: root.tokens.space16
                                topPadding: root.tokens.space16
                                bottomPadding: root.tokens.space16
                                Accessible.role: Accessible.EditableText
                                Accessible.name: qsTr("What Speakr would type")
                                Accessible.description: qsTr("Read only. This is a temporary preview and is never inserted.")

                                background: Rectangle {
                                    radius: root.tokens.radius
                                    color: root.tokens.background
                                    border.width: wouldTypeTranscript.activeFocus ? 2 : 1
                                    border.color: wouldTypeTranscript.activeFocus ? root.tokens.focus : root.tokens.border
                                }
                            }
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: root.tokens.space12

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Retry")
                            enabled: !root.value(root.practice, "active", false)
                                     && !root.value(root.practice, "busy", false)
                            accessibleDescription: qsTr("Start another temporary practice recording")
                            onClicked: bridge.startPractice()
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Clear")
                            enabled: root.heardText().length > 0 || root.wouldTypeText().length > 0
                            accessibleDescription: qsTr("Clear temporary practice text from memory")
                            onClicked: bridge.clearPractice()
                        }
                    }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                columns: width >= root.tokens.metric(650) ? 2 : 1
                columnSpacing: root.tokens.space24
                rowSpacing: root.tokens.space24

                Rectangle {
                    Layout.columnSpan: parent.columns
                    Layout.fillWidth: true
                    visible: root.vocabularyIssueVisible()
                    implicitHeight: practiceVocabularyIssue.implicitHeight + root.tokens.space24
                    radius: root.tokens.radius
                    color: root.vocabularyIssueCode() === "busy_setting"
                           ? root.tokens.warningSurface : root.tokens.dangerSurface
                    border.width: 1
                    border.color: root.vocabularyIssueCode() === "busy_setting"
                                  ? root.tokens.warning : root.tokens.danger
                    Accessible.role: Accessible.AlertMessage
                    Accessible.name: String(root.value(root.vocabularyIssue(), "message", ""))

                    PlainText {
                        id: practiceVocabularyIssue
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: root.tokens.space12
                        text: String(root.value(root.vocabularyIssue(), "message", ""))
                        color: root.vocabularyIssueCode() === "busy_setting"
                               ? root.tokens.warning : root.tokens.danger
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.tokens.space8

                    PlainText {
                        text: qsTr("Add a word")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.sectionHeading
                        font.weight: Font.DemiBold
                        Accessible.role: Accessible.Heading
                    }

                    QuietTextField {
                        id: wordField
                        objectName: "practiceWordField"
                        Layout.fillWidth: true
                        tokens: root.tokens
                        placeholderText: qsTr("Name or specialized word")
                        accessibleName: qsTr("Word to add")
                        onAccepted: root.submitWord()
                    }

                    QuietButton {
                        id: addWordButton
                        tokens: root.tokens
                        text: qsTr("Add word")
                        enabled: wordField.text.trim().length > 0
                        onClicked: root.submitWord()
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.tokens.space8

                    PlainText {
                        text: qsTr("Add a replacement")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.sectionHeading
                        font.weight: Font.DemiBold
                        Accessible.role: Accessible.Heading
                    }

                    QuietTextField {
                        id: heardField
                        objectName: "practiceReplacementHeardField"
                        Layout.fillWidth: true
                        tokens: root.tokens
                        placeholderText: qsTr("What Speakr heard")
                        accessibleName: qsTr("Heard phrase")
                    }

                    QuietTextField {
                        id: intendedField
                        objectName: "practiceReplacementIntendedField"
                        Layout.fillWidth: true
                        tokens: root.tokens
                        placeholderText: qsTr("What you intended")
                        accessibleName: qsTr("Intended phrase")
                        onAccepted: root.submitReplacement()
                    }

                    QuietButton {
                        id: addReplacementButton
                        tokens: root.tokens
                        text: qsTr("Add replacement")
                        enabled: heardField.text.trim().length > 0 && intendedField.text.trim().length > 0
                        onClicked: root.submitReplacement()
                    }
                }
            }

            Item { Layout.preferredHeight: root.tokens.space24 }
        }
    }
}
