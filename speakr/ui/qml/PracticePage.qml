import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    objectName: "practicePage"

    required property var tokens
    property var practice: ({})
    property var appState: ({})
    readonly property int pageMargin: width < tokens.metric(760)
                                      ? tokens.space16 : tokens.space32

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

    function isActive() {
        return Boolean(value(practice, "active", false))
    }

    function isBusy() {
        return Boolean(value(practice, "busy",
                             value(practice, "processing", false)))
    }

    function hasResult() {
        return Boolean(value(practice, "hasResult", false))
                || heardText().length > 0 || wouldTypeText().length > 0
    }

    function attemptExists() {
        return hasResult() || practiceMessage().length > 0
    }

    function levelCount() {
        if (!isActive()) return 0
        var level = String(value(practice, "mic_level_band",
                                 value(practice, "level", "silent")))
        if (level === "high") return 5
        if (level === "good") return 4
        if (level === "low") return 2
        return 0
    }

    function levelLabel() {
        if (!isActive()) {
            if (isBusy()) return qsTr("Processing locally")
            return attemptExists()
                    ? qsTr("Starts when you choose Retry")
                    : qsTr("Starts when you choose Start")
        }
        var level = String(value(practice, "mic_level_band",
                                 value(practice, "level", "silent")))
        if (level === "high") return qsTr("High")
        if (level === "good") return qsTr("Good")
        if (level === "low") return qsTr("Low")
        return qsTr("Waiting for sound")
    }

    function stateLabel() {
        if (isActive())
            return qsTr("Listening")
        if (isBusy())
            return qsTr("Transcribing locally")
        if (hasResult())
            return qsTr("Ready to review")
        if (practiceMessage().length > 0)
            return qsTr("Ready to try again")
        return qsTr("Ready to practice")
    }

    function stateDescription() {
        if (isActive()) {
            return levelCount() > 0
                    ? qsTr("Sound detected. Input level: %1").arg(levelLabel())
                    : qsTr("Waiting for sound")
        }
        if (isBusy())
            return qsTr("Your temporary recording is being processed on this device")
        if (hasResult())
            return qsTr("Review the temporary result, retry, or clear it")
        if (practiceMessage().length > 0)
            return qsTr("Review the message, then retry or clear it")
        return qsTr("Start when you are ready. Nothing is timed.")
    }

    function heardText() {
        return String(value(practice, "heard", value(practice, "text", "")))
    }

    function wouldTypeText() {
        return String(value(practice, "would_type",
                            value(practice, "wouldType", value(practice, "text", ""))))
    }

    function practiceMessage() {
        return String(value(practice, "error", value(practice, "message", "")))
    }

    function messageKind() {
        var message = practiceMessage().toLowerCase()
        if (message.indexOf("microphone") >= 0
                || message.indexOf("could not finish") >= 0)
            return "danger"
        if (message.indexOf("wait") >= 0 || message.indexOf("not ready") >= 0)
            return "warning"
        return "info"
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
        objectName: "practiceScroll"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            spacing: root.tokens.space24

            Item { Layout.preferredHeight: root.tokens.space8 }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.pageMargin
                Layout.rightMargin: root.pageMargin
                spacing: root.tokens.space8

                PlainText {
                    id: pageHeading
                    objectName: "practicePageHeading"
                    Layout.fillWidth: true
                    text: qsTr("Practice")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.pageHeading
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                    Accessible.role: Accessible.Heading
                    Accessible.name: text
                }

                PlainText {
                    Layout.fillWidth: true
                    text: qsTr("Try a private dictation without inserting text anywhere.")
                    color: root.tokens.mutedText
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    wrapMode: Text.Wrap
                }
            }

            GlassSurface {
                id: practiceSurface
                objectName: "practiceCaptureSurface"
                Layout.fillWidth: true
                Layout.leftMargin: root.pageMargin
                Layout.rightMargin: root.pageMargin
                implicitHeight: practiceContent.implicitHeight + padding * 2
                tokens: root.tokens
                role: "major"
                padding: root.tokens.space24

                ColumnLayout {
                    id: practiceContent
                    anchors.fill: parent
                    spacing: root.tokens.space16

                    SectionHeading {
                        Layout.fillWidth: true
                        tokens: root.tokens
                        title: qsTr("Private microphone check")
                        description: qsTr("Use the level only to confirm the microphone is picking up sound.")
                    }

                    InlineNotice {
                        objectName: "practicePrivacyNotice"
                        Layout.fillWidth: true
                        tokens: root.tokens
                        kind: "info"
                        title: qsTr("Temporary by design")
                        message: qsTr("Not stored by Speakr; clears when you leave Practice.")
                        detail: qsTr("Practice never inserts, logs, learns, enters cleanup context, or touches the clipboard.")
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= root.tokens.metric(560) ? 2 : 1
                        columnSpacing: root.tokens.space16
                        rowSpacing: root.tokens.space12

                        StatusOrb {
                            id: practiceStatus
                            objectName: "practiceStatus"
                            Layout.fillWidth: true
                            tokens: root.tokens
                            statusKind: root.isActive() || root.isBusy() ? "active"
                                        : (root.hasResult() ? "success"
                                           : (root.practiceMessage().length > 0
                                              ? "warning" : "neutral"))
                            symbol: root.hasResult() && !root.isBusy()
                                    ? "\u2713"
                                    : (root.practiceMessage().length > 0
                                       && !root.isBusy() ? "!" : "\u2022")
                            label: root.stateLabel()
                            description: root.stateDescription()
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: root.tokens.space8
                            layoutDirection: Qt.RightToLeft

                            QuietButton {
                                objectName: "practiceStartStopButton"
                                visible: root.isActive() || root.isBusy()
                                         || !root.attemptExists()
                                tokens: root.tokens
                                text: root.isActive() ? qsTr("Stop")
                                      : (root.isBusy() ? qsTr("Processing…")
                                                       : qsTr("Start"))
                                kind: root.isBusy() ? "secondary" : "primary"
                                enabled: root.isActive() || !root.isBusy()
                                accessibleDescription: root.isActive()
                                                       ? qsTr("Stop this temporary practice recording")
                                                       : (root.isBusy()
                                                          ? qsTr("Temporary practice is processing locally")
                                                          : qsTr("Start a temporary practice recording"))
                                onClicked: root.isActive()
                                           ? bridge.stopPractice() : bridge.startPractice()
                            }
                        }
                    }

                    RowLayout {
                        id: meter
                        objectName: "practiceMicrophoneMeter"
                        visible: root.isActive()
                        Layout.fillWidth: true
                        spacing: root.tokens.space8
                        Accessible.role: Accessible.ProgressBar
                        Accessible.name: qsTr("Microphone input level: %1").arg(root.levelLabel())
                        Accessible.ignored: !root.isActive()
                        Accessible.description: root.isActive()
                                                ? (root.levelCount() > 0
                                                   ? qsTr("Sound detected")
                                                   : qsTr("Waiting for sound"))
                                                : root.levelLabel()

                        Repeater {
                            objectName: "practiceMeterSegments"
                            model: 5

                            Rectangle {
                                objectName: "practiceMeterSegment"
                                required property int index
                                readonly property bool filled: index < root.levelCount()
                                readonly property color edgeColor: root.tokens.highContrast
                                                                     ? root.tokens.text
                                                                     : (filled ? root.tokens.accent
                                                                               : root.tokens.border)
                                Layout.preferredWidth: root.tokens.metric(32)
                                Layout.preferredHeight: root.tokens.space12
                                radius: root.tokens.radiusSmall
                                color: root.tokens.highContrast
                                       ? (filled ? root.tokens.text
                                                 : root.tokens.surface)
                                       : (filled ? root.tokens.accent
                                                 : root.tokens.surfaceRaised)
                                border.width: root.tokens.borderWidth
                                border.color: edgeColor

                                Behavior on color {
                                    ColorAnimation { duration: root.tokens.motionFast }
                                }
                            }
                        }

                        PlainText {
                            Layout.fillWidth: true
                            text: root.levelLabel()
                            color: root.tokens.mutedText
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.secondary
                            wrapMode: Text.Wrap
                        }
                    }

                    InlineNotice {
                        objectName: "practiceResultNotice"
                        Layout.fillWidth: true
                        visible: root.practiceMessage().length > 0
                        tokens: root.tokens
                        kind: root.messageKind()
                        title: root.messageKind() === "danger"
                               ? qsTr("Practice could not finish")
                               : (root.messageKind() === "warning"
                                  ? qsTr("Practice is not ready yet")
                                  : qsTr("Nothing was added"))
                        message: root.practiceMessage()
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
                                objectName: "practiceHeardTranscript"
                                Layout.fillWidth: true
                                Layout.minimumHeight: root.tokens.metric(160)
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
                                Accessible.description: qsTr("Read only. Held in memory and cleared when Practice closes.")

                                background: Item {
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: root.tokens.radiusControl
                                        color: root.tokens.contentSurface
                                        border.width: root.tokens.borderWidth
                                        border.color: root.tokens.border
                                    }

                                    FocusRing {
                                        anchors.fill: parent
                                        tokens: root.tokens
                                        shown: heardTranscript.activeFocus
                                        cornerRadius: root.tokens.radiusControl
                                    }
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
                                objectName: "practiceWouldTypeTranscript"
                                Layout.fillWidth: true
                                Layout.minimumHeight: root.tokens.metric(160)
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
                                Accessible.description: qsTr("Read only. This temporary preview is never inserted.")

                                background: Item {
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: root.tokens.radiusControl
                                        color: root.tokens.contentSurface
                                        border.width: root.tokens.borderWidth
                                        border.color: root.tokens.border
                                    }

                                    FocusRing {
                                        anchors.fill: parent
                                        tokens: root.tokens
                                        shown: wouldTypeTranscript.activeFocus
                                        cornerRadius: root.tokens.radiusControl
                                    }
                                }
                            }
                        }
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: root.tokens.space12

                        QuietButton {
                            objectName: "practiceRetryButton"
                            visible: root.attemptExists()
                            tokens: root.tokens
                            text: qsTr("Retry")
                            enabled: !root.isActive() && !root.isBusy()
                            accessibleDescription: qsTr("Start another temporary practice recording")
                            onClicked: bridge.startPractice()
                        }

                        QuietButton {
                            objectName: "practiceClearButton"
                            tokens: root.tokens
                            text: qsTr("Clear")
                            enabled: root.hasResult() || root.practiceMessage().length > 0
                            accessibleDescription: qsTr("Clear temporary practice text and messages from memory")
                            onClicked: bridge.clearPractice()
                        }
                    }
                }
            }

            InlineNotice {
                Layout.fillWidth: true
                Layout.leftMargin: root.pageMargin
                Layout.rightMargin: root.pageMargin
                visible: root.vocabularyIssueVisible()
                tokens: root.tokens
                kind: root.vocabularyIssueCode() === "busy_setting"
                      ? "warning" : "danger"
                title: root.vocabularyIssueCode() === "busy_setting"
                       ? qsTr("Vocabulary change is waiting")
                       : qsTr("Vocabulary was not changed")
                message: String(root.value(root.vocabularyIssue(), "message", ""))
                detail: qsTr("Your typed values remain here so you can try again.")
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.pageMargin
                Layout.rightMargin: root.pageMargin
                columns: width >= root.tokens.metric(680) ? 2 : 1
                columnSpacing: root.tokens.space24
                rowSpacing: root.tokens.space24

                GlassSurface {
                    Layout.fillWidth: true
                    implicitHeight: wordContent.implicitHeight + padding * 2
                    tokens: root.tokens
                    role: "major"
                    padding: root.tokens.space16

                    ColumnLayout {
                        id: wordContent
                        anchors.fill: parent
                        spacing: root.tokens.space12

                        SectionHeading {
                            Layout.fillWidth: true
                            tokens: root.tokens
                            title: qsTr("Add a word")
                            description: qsTr("Keep a name or specialized word available for future dictation.")
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
                            accessibleDescription: qsTr("Add this word to manual vocabulary")
                            onClicked: root.submitWord()
                        }
                    }
                }

                GlassSurface {
                    Layout.fillWidth: true
                    implicitHeight: replacementContent.implicitHeight + padding * 2
                    tokens: root.tokens
                    role: "major"
                    padding: root.tokens.space16

                    ColumnLayout {
                        id: replacementContent
                        anchors.fill: parent
                        spacing: root.tokens.space12

                        SectionHeading {
                            Layout.fillWidth: true
                            tokens: root.tokens
                            title: qsTr("Add a replacement")
                            description: qsTr("Tell Speakr which phrase should replace a recurring mishearing.")
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
                            enabled: heardField.text.trim().length > 0
                                     && intendedField.text.trim().length > 0
                            accessibleDescription: qsTr("Add this phrase replacement")
                            onClicked: root.submitReplacement()
                        }
                    }
                }
            }

            Item { Layout.preferredHeight: root.tokens.space24 }
        }
    }
}
