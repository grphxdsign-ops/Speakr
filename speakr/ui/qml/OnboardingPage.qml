import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    objectName: "onboardingPage"

    required property var tokens
    property var appState: ({})
    property var settings: ({})
    property var practice: ({})
    property int currentStep: 0
    property int transitionDirection: 1
    property string selectedModel: String(setting("model", "auto"))
    property bool selectedToggleMode: Boolean(setting("toggle_mode", false))
    readonly property int pageMargin: width < tokens.metric(760)
                                      ? tokens.space16 : tokens.space32
    readonly property var stepNames: [
        qsTr("Privacy"), qsTr("Permissions"), qsTr("Speech model"),
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
            if (source === null || source === undefined
                    || source[parts[i]] === undefined)
                return fallbackValue
            source = source[parts[i]]
        }
        return source === undefined ? fallbackValue : source
    }

    function goTo(step) {
        var bounded = Math.max(0, Math.min(stepNames.length - 1, step))
        if (currentStep === 3 && bounded !== 3 && bridge.capturingHotkey)
            bridge.cancelHotkeyCapture()
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

    function shortcutForcesToggle() {
        return Boolean(setting("toggle_mode_forced", false))
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
        else if (action === "retry_model") bridge.retrySetup()
        else bridge.dismissIssue()
    }

    function next() {
        if (currentStep === 3 && bridge.capturingHotkey)
            return
        if (currentStep === 1 && permissionBlocked())
            return
        if (currentStep === 2 && (modelBusy() || modelFailed()))
            return
        if (currentStep === 2
                && selectedModel !== String(setting("model", "auto"))) {
            if (!bridge.setSetting("model", selectedModel))
                return
            return
        }
        if (currentStep === 3 && !shortcutForcesToggle()
                && !bridge.setSetting("toggle_mode", selectedToggleMode))
            return
        if (currentStep < stepNames.length - 1) {
            goTo(currentStep + 1)
            return
        }
        finishSetup()
    }

    function finishSetup() {
        bridge.stopPractice()
        bridge.clearPractice()
        if (bridge.completeOnboarding())
            completed()
    }

    function modelIndex(modelName) {
        var options = ["auto", "tiny", "base", "small", "medium",
                       "large-v3-turbo", "large-v3"]
        var index = options.indexOf(String(modelName))
        return index < 0 ? 0 : index
    }

    function modelValue(index) {
        var options = ["auto", "tiny", "base", "small", "medium",
                       "large-v3-turbo", "large-v3"]
        return options[Math.max(0, Math.min(options.length - 1, index))]
    }

    function levelCount() {
        if (!practiceActive()) return 0
        var level = String(value(practice, "mic_level_band",
                                 value(practice, "level", "silent")))
        if (level === "high") return 5
        if (level === "good") return 4
        if (level === "low") return 2
        return 0
    }

    function levelLabel() {
        if (!practiceActive()) {
            if (practiceBusy()) return qsTr("Processing locally")
            if (practiceAttemptExists()) return qsTr("Starts when you choose Try again")
            return qsTr("Starts when you choose Start Practice")
        }
        var level = String(value(practice, "mic_level_band",
                                 value(practice, "level", "silent")))
        if (level === "high") return qsTr("High")
        if (level === "good") return qsTr("Good")
        if (level === "low") return qsTr("Low")
        return qsTr("Waiting for sound")
    }

    function practiceText() {
        return String(value(practice, "text",
                            value(practice, "wouldType",
                                  value(practice, "heard", ""))))
    }

    function practiceMessage() {
        return String(value(practice, "error",
                            value(practice, "message", "")))
    }

    function practiceActive() {
        return Boolean(value(practice, "active", false))
    }

    function practiceBusy() {
        return Boolean(value(practice, "busy",
                             value(practice, "processing", false)))
    }

    function practiceAttemptExists() {
        return practiceText().length > 0 || practiceMessage().length > 0
    }

    function practiceHasResult() {
        return practiceText().length > 0
    }

    // Practice result contract: one 220 ms check draw, then a 1.2 s reading
    // window before the action row changes to secondary Try again + primary
    // Finish. Reduced Motion keeps the reading window (motionReading never
    // collapses to zero); only the drawing itself becomes instant.
    readonly property bool practiceResultVisible: practiceText().length > 0
    property bool practiceResultActionsReady: false
    readonly property bool practiceResultPending: practiceResultVisible
                                                  && !practiceResultActionsReady

    onPracticeResultVisibleChanged: {
        if (practiceResultVisible) {
            practiceResultActionsReady = false
            practiceResultReveal.restart()
        } else {
            practiceResultReveal.stop()
            practiceResultActionsReady = false
        }
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
            objectName: "onboardingScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
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
                        Layout.fillWidth: true
                        text: qsTr("Welcome to Speakr")
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
                        text: qsTr("Set up private voice-to-text in five calm steps. Nothing here is timed.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }
                }

                GridLayout {
                    id: setupGrid
                    Layout.fillWidth: true
                    Layout.leftMargin: root.pageMargin
                    Layout.rightMargin: root.pageMargin
                    columns: width >= root.tokens.metric(720) ? 2 : 1
                    columnSpacing: root.tokens.space24
                    rowSpacing: root.tokens.space16

                    OnboardingStepRail {
                        id: stepRail
                        Layout.alignment: Qt.AlignTop
                        Layout.fillWidth: setupGrid.columns === 1
                        Layout.preferredWidth: setupGrid.columns === 1
                                               ? -1 : root.tokens.metric(224)
                        tokens: root.tokens
                        stepNames: root.stepNames
                        currentStep: root.currentStep
                        onStepActivated: function(index) { root.goTo(index) }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        spacing: root.tokens.space16

                        InlineNotice {
                            Layout.fillWidth: true
                            visible: root.issueCode().length > 0
                                     && !root.modelFailed() && !root.permissionBlocked()
                            tokens: root.tokens
                            kind: "danger"
                            title: qsTr("Setup needs attention")
                            message: root.issueMessage()
                            actionText: root.issueActionLabel()
                            actionDescription: qsTr("Recommended recovery action")
                            onActionRequested: root.runIssueAction()
                        }

                        GlassSurface {
                            id: setupCard
                            objectName: "onboardingSetupCard"
                            Layout.fillWidth: true
                            implicitHeight: cardLayout.implicitHeight + padding * 2
                            tokens: root.tokens
                            role: "major"
                            padding: root.tokens.space24

                            ColumnLayout {
                                id: cardLayout
                                anchors.fill: parent
                                spacing: root.tokens.space16
                                transform: Translate { id: pageShift }

                                SectionHeading {
                                    id: stepHeading
                                    objectName: "onboardingStepHeading"
                                    Layout.fillWidth: true
                                    tokens: root.tokens
                                    title: root.stepNames[root.currentStep]
                                    description: qsTr("Step %1 of %2").arg(root.currentStep + 1)
                                                 .arg(root.stepNames.length)
                                    Accessible.role: Accessible.Heading
                                    Accessible.name: qsTr("Setup step %1 of %2: %3")
                                                     .arg(root.currentStep + 1)
                                                     .arg(root.stepNames.length)
                                                     .arg(root.stepNames[root.currentStep])
                                }

                                StackLayout {
                                    id: stepStack
                                    Layout.fillWidth: true
                                    currentIndex: root.currentStep

                                    ColumnLayout {
                                        spacing: root.tokens.space16

                                        StatusOrb {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            statusKind: "success"
                                            symbol: "\u2713"
                                            label: qsTr("Voice to text, on this device")
                                            description: qsTr("Speakr processes dictation locally")
                                        }

                                        Rectangle {
                                            Layout.fillWidth: true
                                            implicitHeight: privacyCopy.implicitHeight + root.tokens.space32
                                            radius: root.tokens.radiusControl
                                            color: root.tokens.contentSurface
                                            border.width: root.tokens.borderWidth
                                            border.color: root.tokens.border

                                            ColumnLayout {
                                                id: privacyCopy
                                                anchors.fill: parent
                                                anchors.margins: root.tokens.space16
                                                spacing: root.tokens.space12

                                                PlainText {
                                                    Layout.fillWidth: true
                                                    text: qsTr("Your voice and dictated text stay on this computer. When Speakr is ready, it may keep a brief moment of microphone audio in memory so it does not miss your first word. That audio is continuously replaced and is not saved by Speakr.")
                                                    color: root.tokens.text
                                                    font.family: root.tokens.fontFamily
                                                    font.pixelSize: root.tokens.body
                                                    wrapMode: Text.Wrap
                                                }

                                                PlainText {
                                                    Layout.fillWidth: true
                                                    text: qsTr("Speakr does not require an account or send usage reports. The first time you use Speakr, it may download a speech model. After that, dictation works locally.")
                                                    color: root.tokens.mutedText
                                                    font.family: root.tokens.fontFamily
                                                    font.pixelSize: root.tokens.secondary
                                                    wrapMode: Text.Wrap
                                                }
                                            }
                                        }

                                        SignalPath {
                                            Layout.fillWidth: true
                                            Layout.maximumWidth: root.tokens.metric(560)
                                            tokens: root.tokens
                                            activeStage: 0
                                        }
                                    }

                                    ColumnLayout {
                                        spacing: root.tokens.space16

                                        StatusOrb {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            statusKind: root.permissionBlocked() ? "danger" : "success"
                                            symbol: root.permissionBlocked() ? "!" : "\u2713"
                                            label: root.permissionBlocked()
                                                   ? qsTr("Permission is needed")
                                                   : qsTr("Microphone access is ready")
                                            description: root.permissionBlocked()
                                                         ? qsTr("Open system settings, make the change, then recheck")
                                                         : qsTr("Audio remains local and in memory")
                                        }

                                        InlineNotice {
                                            id: permissionNotice
                                            objectName: "onboardingPermissionNotice"
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            kind: root.permissionBlocked() ? "danger" : "info"
                                            title: root.permissionBlocked()
                                                   ? qsTr("Speakr cannot use the microphone yet")
                                                   : qsTr("Operating-system permissions")
                                            message: root.permissionBlocked()
                                                     ? qsTr("Open privacy settings and allow microphone access for Speakr.")
                                                     : qsTr("Speakr can use the system microphone locally. macOS may also ask for Accessibility and Input Monitoring so text can be inserted.")
                                            detail: qsTr("Return here after changing a permission and choose Recheck.")
                                            actionText: root.permissionBlocked()
                                                        ? qsTr("Open system settings") : ""
                                            actionDescription: qsTr("Open operating-system privacy and permission settings")
                                            onActionRequested: bridge.openSystemSettings()
                                        }

                                        QuietButton {
                                            objectName: "onboardingRecheckButton"
                                            tokens: root.tokens
                                            text: qsTr("Recheck")
                                            kind: root.permissionBlocked() ? "secondary" : "quiet"
                                            accessibleDescription: qsTr("Retry local microphone and permission checks")
                                            onClicked: bridge.retrySetup()
                                        }
                                    }

                                    ColumnLayout {
                                        spacing: root.tokens.space16

                                        StatusOrb {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            statusKind: root.modelFailed() ? "danger"
                                                        : (root.modelBusy() ? "active" : "success")
                                            symbol: root.modelFailed() ? "!"
                                                    : (root.modelBusy() ? "\u2022" : "\u2713")
                                            label: root.modelFailed()
                                                   ? qsTr("The local model could not be prepared")
                                                   : (root.modelBusy()
                                                      ? qsTr("Getting the speech model ready")
                                                      : qsTr("Local speech model ready"))
                                            description: root.modelBusy()
                                                         ? qsTr("This step has no time limit")
                                                         : qsTr("Your speech is processed on this computer")
                                        }

                                        PlainText {
                                            Layout.fillWidth: true
                                            text: qsTr("Automatic is recommended. Speakr chooses a speech model that fits this computer.")
                                            color: root.tokens.mutedText
                                            font.family: root.tokens.fontFamily
                                            font.pixelSize: root.tokens.body
                                            wrapMode: Text.Wrap
                                        }

                                        QuietComboBox {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            model: [qsTr("Automatic"), "tiny", "base", "small",
                                                    "medium", "large-v3-turbo", "large-v3"]
                                            currentIndex: root.modelIndex(root.selectedModel)
                                            accessibleName: qsTr("Local speech model")
                                            accessibleDescription: qsTr("The selection is applied when you continue")
                                            onActivated: root.selectedModel = root.modelValue(currentIndex)
                                        }

                                        InlineNotice {
                                            id: modelNotice
                                            objectName: "onboardingModelNotice"
                                            Layout.fillWidth: true
                                            visible: root.modelBusy() || root.modelFailed()
                                            tokens: root.tokens
                                            kind: root.modelFailed() ? "danger" : "info"
                                            title: root.modelFailed()
                                                   ? qsTr("Model setup stopped")
                                                   : qsTr("Preparing locally")
                                            message: root.modelFailed()
                                                     ? qsTr("The speech model is not ready. Retry before continuing.")
                                                     : qsTr("Speakr is preparing the local speech model. You can leave this window open as long as needed.")
                                            actionText: root.modelFailed() ? qsTr("Retry") : ""
                                            actionDescription: qsTr("Try preparing the local speech model again")
                                            onActionRequested: bridge.retrySetup()
                                        }
                                    }

                                    ColumnLayout {
                                        spacing: root.tokens.space16

                                        StatusOrb {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            statusKind: bridge.capturingHotkey ? "active" : "success"
                                            symbol: bridge.capturingHotkey ? "\u2022" : "\u2713"
                                            label: bridge.capturingHotkey
                                                   ? qsTr("Waiting for a shortcut")
                                                   : qsTr("Shortcut ready")
                                            description: qsTr("Capture never times out")
                                        }

                                        InlineNotice {
                                            id: captureNotice
                                            objectName: "onboardingHotkeyCaptureNotice"
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            kind: bridge.capturingHotkey ? "info" : "success"
                                            title: bridge.capturingHotkey
                                                   ? qsTr("Press one key")
                                                   : qsTr("Current shortcut")
                                            message: bridge.capturingHotkey
                                                     ? (String(root.value(root.appState, "pending_hotkey", "")).length > 0
                                                        ? qsTr("Captured: %1").arg(root.value(root.appState, "pending_hotkey", ""))
                                                        : (String(root.setting("platform", "windows")) === "mac"
                                                           ? qsTr("Press one modifier key, such as Fn, Control, Option, or Command.")
                                                           : qsTr("Press one key.")))
                                                     : String(root.value(root.appState, "hotkey",
                                                                        root.setting("hotkey", "right ctrl")))
                                            detail: qsTr("There is no time limit. Choose Cancel or press Escape to stop capture.")
                                        }

                                        Flow {
                                            Layout.fillWidth: true
                                            spacing: root.tokens.space8

                                            QuietButton {
                                                objectName: "onboardingCaptureButton"
                                                tokens: root.tokens
                                                text: bridge.capturingHotkey
                                                      ? qsTr("Cancel") : qsTr("Change shortcut")
                                                kind: bridge.capturingHotkey ? "danger" : "secondary"
                                                accessibleDescription: bridge.capturingHotkey
                                                                       ? qsTr("Cancel shortcut capture")
                                                                       : qsTr("Start untimed shortcut capture")
                                                onClicked: bridge.capturingHotkey
                                                           ? bridge.cancelHotkeyCapture()
                                                           : bridge.beginHotkeyCapture()
                                            }

                                            QuietButton {
                                                objectName: "onboardingConfirmHotkeyButton"
                                                visible: bridge.capturingHotkey
                                                         && String(root.value(root.appState, "pending_hotkey", "")).length > 0
                                                tokens: root.tokens
                                                text: qsTr("Use shortcut")
                                                kind: "primary"
                                                accessibleDescription: qsTr("Confirm the captured shortcut")
                                                onClicked: bridge.confirmHotkey()
                                            }
                                        }

                                        HotkeyWarning {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            candidate: String(root.value(root.appState, "pending_hotkey", ""))
                                        }

                                        SectionHeading {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            title: qsTr("Shortcut behavior")
                                            description: root.shortcutForcesToggle()
                                                         ? qsTr("Windows key combinations always use Press to start and stop. Change to a single-key shortcut to choose Hold to speak.")
                                                         : qsTr("Hold is familiar; Press to start and stop can help when holding a key is difficult.")
                                        }

                                        QuietComboBox {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            model: [qsTr("Hold to speak"),
                                                    qsTr("Press to start and stop")]
                                            currentIndex: root.shortcutForcesToggle()
                                                          || root.selectedToggleMode ? 1 : 0
                                            enabled: !root.shortcutForcesToggle()
                                            accessibleName: qsTr("Shortcut behavior")
                                            accessibleDescription: root.shortcutForcesToggle()
                                                                   ? qsTr("This Windows key combination always uses Press to start and stop")
                                                                   : qsTr("Choose Hold or Press to start and stop")
                                            onActivated: root.selectedToggleMode = currentIndex === 1
                                        }
                                    }

                                    ColumnLayout {
                                        spacing: root.tokens.space16

                                        StatusOrb {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            statusKind: root.practiceActive()
                                                        ? "active"
                                                        : (root.practiceBusy()
                                                           ? "active"
                                                           : (root.practiceHasResult()
                                                              ? "success"
                                                              : (root.practiceMessage().length > 0
                                                                 ? "warning" : "neutral")))
                                            symbol: root.practiceActive()
                                                    || root.practiceBusy()
                                                    ? "\u2022"
                                                    : (root.practiceMessage().length > 0
                                                       && !root.practiceHasResult()
                                                       ? "!" : "\u2713")
                                            label: root.practiceActive()
                                                   ? qsTr("Listening")
                                                   : (root.practiceBusy()
                                                      ? qsTr("Transcribing locally")
                                                      : (root.practiceHasResult()
                                                         ? qsTr("Practice result ready")
                                                         : (root.practiceMessage().length > 0
                                                            ? qsTr("Ready to try again")
                                                            : qsTr("Practice is optional"))))
                                            description: root.practiceActive()
                                                         ? qsTr("Microphone input: %1").arg(root.levelLabel())
                                                         : (root.practiceBusy()
                                                            ? qsTr("Temporary audio is being processed on this device")
                                                            : (root.practiceHasResult()
                                                               ? qsTr("Try again or finish setup")
                                                               : (root.practiceMessage().length > 0
                                                                  ? qsTr("Review the message, then try again or finish setup")
                                                                  : qsTr("You can skip Practice and finish setup"))))
                                        }

                                        InlineNotice {
                                            Layout.fillWidth: true
                                            tokens: root.tokens
                                            kind: "info"
                                            title: qsTr("Temporary local practice")
                                            message: qsTr("Practice never inserts text, updates learning, enters cleanup context, touches the clipboard, or writes transcript logs.")
                                            detail: qsTr("Not stored by Speakr; clears when you leave Practice.")
                                        }

                                        RowLayout {
                                            id: practiceMeter
                                            objectName: "onboardingPracticeMeter"
                                            visible: root.practiceActive()
                                            Layout.fillWidth: true
                                            spacing: root.tokens.space8
                                            Accessible.role: Accessible.ProgressBar
                                            Accessible.name: qsTr("Microphone input level: %1").arg(root.levelLabel())
                                            Accessible.ignored: !root.practiceActive()

                                            Repeater {
                                                objectName: "onboardingPracticeMeterSegments"
                                                model: 5

                                                Rectangle {
                                                    objectName: "onboardingPracticeMeterSegment"
                                                    required property int index
                                                    readonly property bool filled: index < root.levelCount()
                                                    readonly property color edgeColor: root.tokens.highContrast
                                                                                         ? root.tokens.text
                                                                                         : (filled ? root.tokens.accent
                                                                                                   : root.tokens.border)
                                                    Layout.preferredWidth: root.tokens.metric(28)
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

                                        Flow {
                                            Layout.fillWidth: true
                                            spacing: root.tokens.space8

                                            QuietButton {
                                                objectName: "onboardingPracticeStartButton"
                                                tokens: root.tokens
                                                // During the reading window the action row holds its
                                                // processing presentation; it only changes to
                                                // secondary Try again once the pause completes.
                                                text: root.practiceActive()
                                                      ? qsTr("Stop Practice")
                                                      : (root.practiceBusy()
                                                         || root.practiceResultPending
                                                         ? qsTr("Processing…")
                                                         : (root.practiceAttemptExists()
                                                            ? qsTr("Try again")
                                                            : qsTr("Start Practice")))
                                                kind: root.practiceBusy()
                                                      || root.practiceAttemptExists()
                                                      ? "secondary" : "primary"
                                                enabled: !root.practiceBusy()
                                                         && !root.practiceResultPending
                                                // DESIGN.md press contract: scale never below .99,
                                                // 100 ms (tokens.motionFast; instant when reduced).
                                                scale: down && enabled ? 0.99 : 1
                                                accessibleDescription: root.practiceActive()
                                                                       ? qsTr("Stop this temporary practice recording")
                                                                       : (root.practiceBusy()
                                                                          || root.practiceResultPending
                                                                          ? qsTr("Temporary practice is processing locally")
                                                                          : (root.practiceAttemptExists()
                                                                          ? qsTr("Start another temporary practice recording")
                                                                          : qsTr("Start a temporary practice recording")))
                                                onClicked: root.practiceActive()
                                                           ? bridge.stopPractice()
                                                           : bridge.startPractice()

                                                Behavior on scale {
                                                    NumberAnimation {
                                                        duration: root.tokens.motionFast
                                                        easing.type: Easing.OutQuint
                                                    }
                                                }
                                            }

                                            QuietButton {
                                                objectName: "onboardingPracticeClearButton"
                                                tokens: root.tokens
                                                text: qsTr("Clear")
                                                enabled: root.practiceAttemptExists()
                                                         && !root.practiceResultPending
                                                accessibleDescription: qsTr("Clear temporary practice text from memory")
                                                onClicked: bridge.clearPractice()
                                            }
                                        }

                                        InlineNotice {
                                            Layout.fillWidth: true
                                            visible: root.practiceMessage().length > 0
                                            tokens: root.tokens
                                            kind: "warning"
                                            title: qsTr("Practice did not finish")
                                            message: root.practiceMessage()
                                        }

                                        RowLayout {
                                            objectName: "onboardingPracticeResultCheck"
                                            visible: root.practiceResultVisible
                                            Layout.fillWidth: true
                                            spacing: root.tokens.space8

                                            CheckDraw {
                                                objectName: "onboardingPracticeResultCheckDraw"
                                                Layout.preferredWidth: root.tokens.metric(16)
                                                Layout.preferredHeight: root.tokens.metric(16)
                                                tokens: root.tokens
                                                drawn: root.practiceResultVisible
                                                strokeColor: root.tokens.highContrast
                                                             ? root.tokens.text
                                                             : root.tokens.accentForeground
                                            }

                                            PlainText {
                                                Layout.fillWidth: true
                                                text: qsTr("Cleaned up locally")
                                                color: root.tokens.text
                                                font.family: root.tokens.fontFamily
                                                font.pixelSize: root.tokens.secondary
                                                font.weight: Font.DemiBold
                                                wrapMode: Text.Wrap
                                            }
                                        }

                                        PlainTextArea {
                                            id: practiceResult
                                            objectName: "onboardingPracticeResult"
                                            Layout.fillWidth: true
                                            Layout.minimumHeight: root.tokens.metric(150)
                                            readOnly: true
                                            text: root.practiceText()
                                            placeholderText: qsTr("Your temporary practice text will appear here.")
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
                                            Accessible.name: qsTr("Temporary practice transcript")
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
                                                    shown: practiceResult.activeFocus
                                                    cornerRadius: root.tokens.radiusControl
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Item { Layout.preferredHeight: root.tokens.space24 }
            }
        }

        GlassSurface {
            id: setupFooter
            objectName: "onboardingFooter"
            Layout.fillWidth: true
            implicitHeight: footerLayout.implicitHeight + padding * 2
            tokens: root.tokens
            role: "notice"
            cornerRadius: root.tokens.radiusControl
            elevated: false
            padding: root.tokens.space12

            GridLayout {
                id: footerLayout
                anchors.fill: parent
                columns: width >= root.tokens.metric(520) ? 2 : 1
                columnSpacing: root.tokens.space16
                rowSpacing: root.tokens.space8

                QuietButton {
                    objectName: "onboardingBackButton"
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
                        objectName: "onboardingContinueButton"
                        visible: root.currentStep < root.stepNames.length - 1
                                 || (root.currentStep === root.stepNames.length - 1
                                     && root.practiceAttemptExists()
                                     && !root.practiceActive()
                                     && !root.practiceBusy()
                                     && !root.practiceResultPending)
                        tokens: root.tokens
                        text: root.currentStep === root.stepNames.length - 1
                              ? qsTr("Finish setup") : qsTr("Continue")
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
                        id: skipPracticeButton
                        objectName: "skipPracticeButton"
                        visible: root.currentStep === root.stepNames.length - 1
                                 && (!root.practiceAttemptExists()
                                     || root.practiceResultPending)
                        tokens: root.tokens
                        text: qsTr("Skip Practice and finish setup")
                        enabled: !root.practiceActive() && !root.practiceBusy()
                                 && !root.practiceResultPending
                        accessibleDescription: qsTr("Finish setup without a practice dictation")
                        onClicked: root.finishSetup()
                    }
                }
            }
        }
    }

    SequentialAnimation {
        id: practiceResultReveal

        // The pause is the DESIGN.md reading window, not fake progress: the
        // result and its check draw are already visible while it runs. Only
        // the action row waits so the result can be read before focus
        // targets move.
        PauseAnimation { duration: root.tokens.motionReading }
        ScriptAction { script: root.practiceResultActionsReady = true }
    }

    ParallelAnimation {
        id: transition

        NumberAnimation {
            target: cardLayout
            property: "opacity"
            from: root.tokens.reduceMotion ? 1 : 0
            to: 1
            duration: root.tokens.motionOnboarding
            easing.type: Easing.OutQuint
        }

        NumberAnimation {
            target: pageShift
            property: "x"
            from: root.tokens.reduceMotion
                  ? 0 : root.tokens.space12 * root.transitionDirection
            to: 0
            duration: root.tokens.motionOnboarding
            easing.type: Easing.OutQuint
        }
    }

    Component.onCompleted: {
        // A result that already exists when the page loads was read earlier;
        // only newly arriving results replay the check draw and reading pause.
        if (practiceResultVisible)
            practiceResultActionsReady = true
        stepHeading.forceActiveFocus(Qt.OtherFocusReason)
    }
}
