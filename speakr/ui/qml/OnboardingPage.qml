import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var tokens
    property var appState: ({})
    property var settings: ({})
    property var practice: ({})
    property int currentStep: 0
    property int transitionDirection: 1
    property string selectedModel: String(setting("model", "auto"))
    property bool selectedToggleMode: Boolean(setting("toggle_mode", false))
    readonly property var stepNames: [
        qsTr("Privacy"), qsTr("Microphone"), qsTr("Model"),
        qsTr("Shortcut"), qsTr("Practice")
    ]

    signal completed()

    function value(source, key, fallbackValue) {
        if (source !== null && source !== undefined
                && source[key] !== null && source[key] !== undefined)
            return source[key]
        return fallbackValue
    }

    function setting(path, fallbackValue) {
        var source = settings || ({})
        if (source[path] !== undefined && source[path] !== null)
            return source[path]
        var parts = path.split(".")
        for (var i = 0; i < parts.length; ++i) {
            if (source === null || source === undefined || source[parts[i]] === undefined)
                return fallbackValue
            source = source[parts[i]]
        }
        return source === undefined ? fallbackValue : source
    }

    function goTo(step) {
        var bounded = Math.max(0, Math.min(stepNames.length - 1, step))
        if (currentStep === 4 && bounded !== 4) {
            bridge.stopPractice()
            bridge.clearPractice()
        }
        transitionDirection = bounded >= currentStep ? 1 : -1
        currentStep = bounded
        transition.restart()
        stepHeading.forceActiveFocus(Qt.TabFocusReason)
    }

    function issueCode() {
        var issue = value(appState, "last_issue", null)
        return issue && issue.code !== undefined ? String(issue.code) : ""
    }

    function modelBusy() {
        return String(value(appState, "pipeline", "idle")) === "waiting_model"
                || String(value(appState, "availability", "ready")) === "starting"
    }

    function modelFailed() {
        return ["model_unavailable", "model_load_failed"].indexOf(issueCode()) >= 0
    }

    function permissionBlocked() {
        return ["microphone_unavailable", "permission_missing"].indexOf(issueCode()) >= 0
    }

    function issueAction() {
        var issue = value(appState, "last_issue", null)
        return issue && issue.action !== undefined ? String(issue.action) : ""
    }

    function issueMessage() {
        var issue = value(appState, "last_issue", null)
        return issue && issue.message !== undefined ? String(issue.message) : ""
    }

    function issueActionLabel() {
        var action = issueAction()
        if (action === "open_config") return qsTr("Open local config")
        if (action === "open_dictionary") return qsTr("Open local dictionary")
        if (action === "open_log") return qsTr("Open local log")
        if (action === "choose_hotkey") return qsTr("Choose another shortcut")
        if (action === "open_system_settings") return qsTr("Open system settings")
        if (action === "reload_dictionary") return qsTr("Reload Vocabulary")
        if (action === "start_practice") return qsTr("Start Practice")
        if (action === "open_speakr") return qsTr("Dismiss")
        if (action === "retry_model") return qsTr("Retry")
        if (action === "try_again") return qsTr("Try again")
        return qsTr("Dismiss")
    }

    function runIssueAction() {
        var action = issueAction()
        if (action === "open_config") bridge.openLocal("config")
        else if (action === "open_dictionary") bridge.openLocal("dictionary")
        else if (action === "open_log") bridge.openLocal("log")
        else if (action === "choose_hotkey") goTo(3)
        else if (action === "open_system_settings") bridge.openSystemSettings()
        else if (action === "reload_dictionary") bridge.reloadLocalState()
        else if (action === "start_practice") goTo(4)
        else if (action === "open_speakr") bridge.dismissIssue()
        else if (action === "retry_model") bridge.retrySetup()
        else if (action === "try_again") bridge.dismissIssue()
        else bridge.dismissIssue()
    }

    function next() {
        if (currentStep === 3 && bridge.capturingHotkey)
            return
        if (currentStep === 1 && permissionBlocked())
            return
        if (currentStep === 2 && (modelBusy() || modelFailed()))
            return
        if (currentStep === 2 && selectedModel !== String(setting("model", "auto"))) {
            if (!bridge.setSetting("model", selectedModel))
                return
            // Applying a different model begins a truthful local loading
            // state. Stay here until it is ready or exposes Retry.
            return
        }
        if (currentStep === 3) {
            if (!bridge.setSetting("toggle_mode", selectedToggleMode))
                return
        }
        if (currentStep < stepNames.length - 1) {
            goTo(currentStep + 1)
            return
        }
        bridge.stopPractice()
        bridge.clearPractice()
        if (bridge.completeOnboarding())
            completed()
    }

    function modelIndex(value) {
        var options = ["auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]
        var index = options.indexOf(String(value))
        return index < 0 ? 0 : index
    }

    function modelValue(index) {
        var options = ["auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]
        return options[Math.max(0, Math.min(options.length - 1, index))]
    }

    function levelCount() {
        var level = String(value(practice, "mic_level_band", value(appState, "mic_level_band", "silent")))
        if (level === "high") return 5
        if (level === "good") return 4
        if (level === "low") return 2
        return 0
    }

    Keys.onEscapePressed: function(event) {
        if (bridge.capturingHotkey) {
            bridge.cancelHotkeyCapture()
            event.accepted = true
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
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
                        Layout.fillWidth: true
                        text: qsTr("Welcome to Speakr")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.pageHeading
                        font.weight: Font.DemiBold
                        Accessible.role: Accessible.Heading
                        Accessible.name: text
                    }

                    PlainText {
                        Layout.fillWidth: true
                        text: qsTr("Set up private voice-to-text in five short steps. Nothing here is timed.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    Layout.leftMargin: root.tokens.space32
                    Layout.rightMargin: root.tokens.space32
                    spacing: root.tokens.space4
                    Accessible.role: Accessible.PageTabList
                    Accessible.name: qsTr("Setup steps")

                    Repeater {
                        model: root.stepNames

                        delegate: Row {
                            required property int index
                            required property string modelData
                            spacing: root.tokens.space4

                            NavigationButton {
                                tokens: root.tokens
                                text: qsTr("%1. %2").arg(index + 1).arg(modelData)
                                selected: root.currentStep === index
                                enabled: index <= root.currentStep
                                Accessible.description: root.currentStep === index
                                                        ? qsTr("Current setup step")
                                                        : qsTr("Go to setup step %1").arg(index + 1)
                                onClicked: root.goTo(index)
                            }

                            PlainText {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: index < root.stepNames.length - 1
                                text: "→"
                                color: root.tokens.mutedText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                Accessible.ignored: true
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.leftMargin: root.tokens.space32
                    Layout.rightMargin: root.tokens.space32
                    visible: root.issueCode().length > 0
                             && !root.modelFailed() && !root.permissionBlocked()
                    implicitHeight: setupIssueContent.implicitHeight + root.tokens.space24
                    radius: root.tokens.radius
                    color: root.tokens.dangerSurface
                    border.width: 1
                    border.color: root.tokens.danger
                    Accessible.role: Accessible.AlertMessage
                    Accessible.name: root.issueMessage()

                    GridLayout {
                        id: setupIssueContent
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: root.tokens.space12
                        columns: width >= root.tokens.metric(520) ? 2 : 1
                        columnSpacing: root.tokens.space16
                        rowSpacing: root.tokens.space8

                        PlainText {
                            Layout.fillWidth: true
                            text: root.issueMessage()
                            color: root.tokens.danger
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.body
                            wrapMode: Text.Wrap
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: root.issueActionLabel()
                            kind: "primary"
                            accessibleDescription: qsTr("Recommended recovery action for the setup issue")
                            onClicked: root.runIssueAction()
                        }
                    }
                }

                ColumnLayout {
                    id: animatedContent
                    Layout.fillWidth: true
                    Layout.leftMargin: root.tokens.space32
                    Layout.rightMargin: root.tokens.space32
                    spacing: root.tokens.space16
                    transform: Translate { id: pageShift }

                    PlainText {
                        id: stepHeading
                        Layout.fillWidth: true
                        text: root.stepNames[root.currentStep]
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.sectionHeading
                        font.weight: Font.DemiBold
                        Accessible.role: Accessible.Heading
                        Accessible.name: qsTr("Setup step %1 of %2: %3")
                                         .arg(root.currentStep + 1)
                                         .arg(root.stepNames.length)
                                         .arg(text)
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        // The implementation keeps the detailed frames grouped by
                        // concern while presenting the explicit setup order:
                        // Privacy → Microphone → Model → Shortcut → Practice.
                        currentIndex: root.currentStep === 1 ? 2
                                      : (root.currentStep === 2 ? 1 : root.currentStep)

                        ColumnLayout {
                            spacing: root.tokens.space16

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: privacyBody.implicitHeight + root.tokens.space32
                                radius: root.tokens.radiusLarge
                                color: root.tokens.successSurface
                                border.width: 1
                                border.color: root.tokens.success

                                ColumnLayout {
                                    id: privacyBody
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.margins: root.tokens.space16
                                    spacing: root.tokens.space12

                                    PlainText {
                                        Layout.fillWidth: true
                                        text: qsTr("Voice to text, on this device")
                                        color: root.tokens.text
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.statusHeading
                                        font.weight: Font.DemiBold
                                        wrapMode: Text.Wrap
                                        Accessible.role: Accessible.Heading
                                    }

                                    PlainText {
                                        Layout.fillWidth: true
                                        text: qsTr("Audio stays in memory. Transcripts, screen context, vocabulary, and diagnostics stay on this computer. Speakr has no accounts, telemetry, analytics, or cloud fallback.")
                                        color: root.tokens.text
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.body
                                        wrapMode: Text.Wrap
                                    }

                                    PlainText {
                                        Layout.fillWidth: true
                                        text: qsTr("The only non-loopback network activity is a one-time speech-model download from Hugging Face. Optional Ollama cleanup uses 127.0.0.1 and is never required.")
                                        color: root.tokens.mutedText
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.secondary
                                        wrapMode: Text.Wrap
                                    }
                                }
                            }

                            SignalPath {
                                Layout.fillWidth: true
                                Layout.maximumWidth: root.tokens.metric(520)
                                tokens: root.tokens
                                activeStage: 0
                            }
                        }

                        ColumnLayout {
                            spacing: root.tokens.space16

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("Choose a local speech model")
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.statusHeading
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                                Accessible.role: Accessible.Heading
                            }

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("Automatic is recommended. It selects a model for the available local hardware and safely falls back to CPU.")
                                color: root.tokens.mutedText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                wrapMode: Text.Wrap
                            }

                            QuietComboBox {
                                tokens: root.tokens
                                model: [qsTr("Automatic"), "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]
                                currentIndex: root.modelIndex(root.selectedModel)
                                accessibleName: qsTr("Local speech model")
                                accessibleDescription: qsTr("The selection is applied when you continue")
                                onActivated: root.selectedModel = root.modelValue(currentIndex)
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: modelStatus.implicitHeight + root.tokens.space24
                                radius: root.tokens.radius
                                color: root.tokens.surface
                                border.width: 1
                                border.color: root.tokens.border

                                PlainText {
                                    id: modelStatus
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.margins: root.tokens.space12
                                    text: root.modelFailed()
                                          ? qsTr("The local speech model could not be prepared. Retry before continuing.")
                                          : (root.modelBusy()
                                             ? qsTr("Getting the local speech model ready. This step has no time limit.")
                                             : qsTr("Local model setting is ready."))
                                    color: root.tokens.mutedText
                                    font.family: root.tokens.fontFamily
                                    font.pixelSize: root.tokens.secondary
                                    wrapMode: Text.Wrap
                                    Accessible.name: text
                                }
                            }

                            QuietButton {
                                visible: root.modelFailed()
                                tokens: root.tokens
                                text: qsTr("Retry")
                                kind: "primary"
                                accessibleDescription: qsTr("Try preparing the local speech model again")
                                onClicked: bridge.retrySetup()
                            }
                        }

                        ColumnLayout {
                            spacing: root.tokens.space16

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("Check microphone access")
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.statusHeading
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                                Accessible.role: Accessible.Heading
                            }

                            PlainText {
                                Layout.fillWidth: true
                                text: root.permissionBlocked()
                                      ? qsTr("Microphone or accessibility permission needs attention. Open system settings, make the change, then recheck.")
                                      : qsTr("Speakr can use the system microphone locally. On macOS, text insertion may also require Accessibility and Input Monitoring permissions.")
                                color: root.permissionBlocked()
                                       ? root.tokens.danger : root.tokens.mutedText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                wrapMode: Text.Wrap
                                Accessible.role: root.permissionBlocked()
                                                 ? Accessible.AlertMessage : Accessible.StaticText
                                Accessible.name: text
                            }

                            Flow {
                                Layout.fillWidth: true
                                spacing: root.tokens.space12

                                QuietButton {
                                    tokens: root.tokens
                                    text: qsTr("Open system settings")
                                    kind: root.permissionBlocked()
                                          ? "primary" : "secondary"
                                    accessibleDescription: qsTr("Open operating system privacy and permission settings")
                                    onClicked: bridge.openSystemSettings()
                                }

                                QuietButton {
                                    tokens: root.tokens
                                    text: qsTr("Recheck")
                                    accessibleDescription: qsTr("Retry local microphone and permission checks")
                                    onClicked: bridge.retrySetup()
                                }
                            }
                        }

                        ColumnLayout {
                            spacing: root.tokens.space16

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("Choose how dictation starts")
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.statusHeading
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                                Accessible.role: Accessible.Heading
                            }

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("Shortcut capture never times out. Select Cancel or press Escape if you change your mind.")
                                color: root.tokens.mutedText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                wrapMode: Text.Wrap
                            }

                            ColumnLayout {
                                spacing: root.tokens.space8

                                PlainText {
                                    text: bridge.capturingHotkey
                                          ? (String(root.value(root.appState, "pending_hotkey", "")).length > 0
                                             ? qsTr("Captured: %1").arg(root.value(root.appState, "pending_hotkey", ""))
                                             : qsTr("Press your new shortcut"))
                                          : qsTr("Current shortcut: %1").arg(root.value(root.appState, "hotkey", root.setting("hotkey", "right ctrl")))
                                    color: root.tokens.text
                                    font.family: root.tokens.fontFamily
                                    font.pixelSize: root.tokens.body
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.Wrap
                                    Accessible.name: text
                                }

                                Flow {
                                    spacing: root.tokens.space8

                                    QuietButton {
                                        tokens: root.tokens
                                        text: bridge.capturingHotkey ? qsTr("Cancel") : qsTr("Change shortcut")
                                        kind: bridge.capturingHotkey ? "danger" : "secondary"
                                        onClicked: bridge.capturingHotkey
                                                   ? bridge.cancelHotkeyCapture() : bridge.beginHotkeyCapture()
                                    }

                                    QuietButton {
                                        visible: bridge.capturingHotkey
                                                 && String(root.value(root.appState, "pending_hotkey", "")).length > 0
                                        tokens: root.tokens
                                        text: qsTr("Use shortcut")
                                        kind: "primary"
                                        onClicked: bridge.confirmHotkey()
                                    }
                                }

                                HotkeyWarning {
                                    Layout.fillWidth: true
                                    tokens: root.tokens
                                    candidate: String(root.value(root.appState, "pending_hotkey", ""))
                                }
                            }

                            PlainText {
                                text: qsTr("Shortcut behavior")
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                font.weight: Font.DemiBold
                            }

                            QuietComboBox {
                                tokens: root.tokens
                                model: [qsTr("Hold to speak"), qsTr("Press to start and stop")]
                                currentIndex: root.selectedToggleMode ? 1 : 0
                                accessibleName: qsTr("Shortcut behavior")
                                onActivated: root.selectedToggleMode = currentIndex === 1
                            }
                        }

                        ColumnLayout {
                            spacing: root.tokens.space16

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("Try a private practice dictation")
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.statusHeading
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                                Accessible.role: Accessible.Heading
                            }

                            PlainText {
                                Layout.fillWidth: true
                                text: qsTr("Practice is optional. It never inserts text, updates learning, enters cleanup context, touches the clipboard, or writes transcript logs.")
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

                            RowLayout {
                                spacing: root.tokens.space8
                                Accessible.role: Accessible.ProgressBar
                                Accessible.name: qsTr("Microphone input level")

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
                                    }
                                }
                            }

                            QuietButton {
                                tokens: root.tokens
                                text: root.value(root.practice, "active", false) ? qsTr("Stop Practice") : qsTr("Start Practice")
                                kind: root.value(root.practice, "active", false) ? "secondary" : "primary"
                                enabled: !root.value(root.practice, "busy", false)
                                onClicked: root.value(root.practice, "active", false)
                                           ? bridge.stopPractice() : bridge.startPractice()
                            }

                            PlainText {
                                Layout.fillWidth: true
                                visible: String(root.value(root.practice, "error", "")).length > 0
                                text: String(root.value(root.practice, "error", ""))
                                color: root.tokens.danger
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                wrapMode: Text.Wrap
                                Accessible.role: Accessible.AlertMessage
                                Accessible.name: text
                            }

                            PlainTextArea {
                                Layout.fillWidth: true
                                Layout.minimumHeight: root.tokens.metric(140)
                                readOnly: true
                                text: root.value(root.practice, "text", "")
                                placeholderText: qsTr("Your temporary practice text will appear here.")
                                wrapMode: TextEdit.Wrap
                                color: root.tokens.text
                                placeholderTextColor: root.tokens.mutedText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                leftPadding: root.tokens.space16
                                rightPadding: root.tokens.space16
                                topPadding: root.tokens.space16
                                bottomPadding: root.tokens.space16
                                Accessible.role: Accessible.EditableText
                                Accessible.name: qsTr("Temporary practice transcript")

                                background: Rectangle {
                                    radius: root.tokens.radius
                                    color: root.tokens.surface
                                    border.width: 1
                                    border.color: root.tokens.border
                                }
                            }

                            QuietButton {
                                tokens: root.tokens
                                text: qsTr("Clear")
                                enabled: String(root.value(root.practice, "text", "")).length > 0
                                accessibleDescription: qsTr("Clear temporary practice text from memory")
                                onClicked: bridge.clearPractice()
                            }
                        }
                    }
                }

                Item { Layout.preferredHeight: root.tokens.space24 }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: footer.implicitHeight + root.tokens.space24
            color: root.tokens.surface
            border.width: 1
            border.color: root.tokens.border

            GridLayout {
                id: footer
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: root.tokens.space12
                columns: width >= root.tokens.metric(520) ? 2 : 1
                columnSpacing: root.tokens.space16
                rowSpacing: root.tokens.space8

                QuietButton {
                    visible: root.currentStep > 0
                    tokens: root.tokens
                    text: qsTr("Back")
                    accessibleDescription: qsTr("Return to the previous setup step")
                    onClicked: root.goTo(root.currentStep - 1)
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: root.tokens.space8
                    layoutDirection: Qt.RightToLeft

                    QuietButton {
                        tokens: root.tokens
                        text: root.currentStep === root.stepNames.length - 1 ? qsTr("Finish setup") : qsTr("Continue")
                        kind: "primary"
                        enabled: !(root.currentStep === 3 && bridge.capturingHotkey)
                                 && !(root.currentStep === 1 && root.permissionBlocked())
                                 && !(root.currentStep === 2
                                      && (root.modelBusy() || root.modelFailed()))
                        accessibleDescription: root.currentStep === root.stepNames.length - 1
                                               ? qsTr("Finish setup and open Home")
                                               : qsTr("Continue to the next setup step")
                        onClicked: root.next()
                    }

                    QuietButton {
                        visible: root.currentStep === root.stepNames.length - 1
                        tokens: root.tokens
                        text: qsTr("Skip Practice")
                        accessibleDescription: qsTr("Finish setup without a practice dictation")
                        onClicked: root.next()
                    }
                }
            }
        }
    }

    ParallelAnimation {
        id: transition
        NumberAnimation {
            target: animatedContent
            property: "opacity"
            from: root.tokens.reduceMotion ? 1 : 0
            to: 1
            duration: root.tokens.reduceMotion ? 0 : 180
            easing.type: Easing.OutQuint
        }
        NumberAnimation {
            target: pageShift
            property: "x"
            from: root.tokens.reduceMotion ? 0 : root.tokens.metric(12) * root.transitionDirection
            to: 0
            duration: root.tokens.reduceMotion ? 0 : 180
            easing.type: Easing.OutQuint
        }
    }

    Component.onCompleted: stepHeading.forceActiveFocus(Qt.OtherFocusReason)
}
