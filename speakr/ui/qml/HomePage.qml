pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var tokens
    property var appState: ({})
    property var settings: ({})
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
        return source === null || source === undefined ? fallbackValue : source
    }

    function statusText() {
        if (value(appState, "availability", "starting") === "needs_attention")
            return value(appState, "primary", qsTr("Speakr needs attention"))
        if (value(appState, "capture", "idle") === "listening")
            return value(appState, "capture_mode", value(appState, "mode", "dictation")) === "edit"
                    ? qsTr("Listening for an edit instruction") : qsTr("Listening")
        var pipeline = value(appState, "pipeline", "idle")
        if (pipeline === "waiting_model") return qsTr("Waiting for the speech model")
        if (pipeline === "transcribing") return qsTr("Transcribing locally")
        if (pipeline === "formatting") return value(appState, "pipeline_mode",
                                                     value(appState, "mode", "dictation")) === "edit"
                    ? qsTr("Applying your instruction locally") : qsTr("Cleaning up locally")
        if (pipeline === "injecting") return qsTr("Inserting text")
        if (pipeline === "success") return value(appState, "pipeline_mode",
                                                  value(appState, "mode", "dictation")) === "edit"
                    ? qsTr("Selection updated") : qsTr("Inserted")
        if (pipeline === "error") return value(appState, "primary", qsTr("Nothing was inserted"))
        var statusCode = String(value(appState, "status_code", "ready"))
        if (["no_speech", "mic_recovery", "edit_failure",
             "formatting_fallback", "gpu_fallback"].indexOf(statusCode) >= 0)
            return value(appState, "primary", qsTr("Ready"))
        if (!value(appState, "enabled", true)) return qsTr("Dictation is off")
        if (value(appState, "availability", "starting") === "starting") return qsTr("Getting Speakr ready")
        return qsTr("Ready")
    }

    function statusDetail() {
        var custom = value(appState, "secondary", "")
        if (custom.length > 0) return custom
        if (value(appState, "availability", "starting") === "needs_attention")
            return qsTr("Use the recovery action below, then try again.")
        if (value(appState, "capture", "idle") === "listening")
            return qsTr("Speak naturally. Release the shortcut when you are finished.")
        if (value(appState, "pipeline", "idle") !== "idle")
            return qsTr("Your audio and text remain on this device.")
        var statusCode = String(value(appState, "status_code", "ready"))
        if (statusCode === "gpu_fallback")
            return qsTr("The local GPU was unavailable. Dictation continues on CPU.")
        if (statusCode === "formatting_fallback")
            return qsTr("Optional Ollama cleanup is unavailable. Basic cleanup remains active.")
        if (statusCode === "no_speech") return qsTr("Try again when you are ready.")
        return qsTr("Hold your shortcut, speak, then release to insert text.")
    }

    function statusIsError() {
        return value(appState, "availability", "starting") === "needs_attention"
                || value(appState, "pipeline", "idle") === "error"
    }

    function statusIsWarning() {
        return ["no_speech", "mic_recovery", "edit_failure",
                "formatting_fallback", "gpu_fallback"]
                .indexOf(String(value(appState, "status_code", "ready"))) >= 0
    }

    function statusKind() {
        if (statusIsError()) return "danger"
        if (statusIsWarning()) return "warning"
        if (!value(appState, "enabled", true)) return "neutral"
        if (value(appState, "capture", "idle") === "listening") return "active"
        var pipeline = value(appState, "pipeline", "idle")
        return pipeline === "success" || (pipeline === "idle"
                                          && value(appState, "availability", "starting") === "ready")
                ? "success" : "active"
    }

    function issueAction() {
        var issue = value(appState, "last_issue", null)
        return issue && issue.action !== undefined ? String(issue.action) : ""
    }

    function issueActionLabel() {
        var action = issueAction()
        if (action === "open_system_settings") return qsTr("Open system settings")
        if (action === "open_log") return qsTr("Open local log")
        if (action === "open_config") return qsTr("Open local config")
        if (action === "open_dictionary") return qsTr("Open local dictionary")
        if (action === "choose_hotkey") return qsTr("Choose another shortcut")
        if (action === "edit_vocabulary") return qsTr("Open Vocabulary")
        if (action === "start_practice") return qsTr("Start Practice")
        if (action === "reload_dictionary") return qsTr("Reload Vocabulary")
        if (action === "dismiss" || action === "open_speakr") return qsTr("Dismiss")
        return qsTr("Try again")
    }

    function runIssueAction() {
        var action = issueAction()
        if (action === "open_system_settings") bridge.openSystemSettings()
        else if (action === "open_log") bridge.openLocal("log")
        else if (action === "open_config") bridge.openLocal("config")
        else if (action === "open_dictionary") bridge.openLocal("dictionary")
        else if (action === "choose_hotkey") bridge.beginHotkeyCapture()
        else if (action === "edit_vocabulary") navigateRequested("vocabulary")
        else if (action === "start_practice") navigateRequested("practice")
        else if (action === "reload_dictionary") bridge.reloadLocalState()
        else if (action === "dismiss" || action === "open_speakr"
                 || action === "try_again") bridge.dismissIssue()
        else bridge.retrySetup()
    }

    function stage() {
        var pipeline = value(appState, "pipeline", "idle")
        if (pipeline === "waiting_model" || pipeline === "transcribing") return 1
        if (pipeline === "formatting") return 2
        if (pipeline === "injecting") return 3
        if (pipeline === "success") return 4
        return 0
    }

    function displayHotkey() {
        var hotkey = String(value(appState, "hotkey", setting("hotkey", "right ctrl")))
        return hotkey.split(" ").map(function(part) {
            return part.length > 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part
        }).join(" ")
    }

    function microphoneSummary() {
        var activeValue = setting("active_input_device", "")
        var configuredValue = setting("input_device", "")
        var active = activeValue === null || activeValue === undefined ? "" : String(activeValue)
        var configured = configuredValue === null || configuredValue === undefined
                         ? "" : String(configuredValue)
        var activeLabel = active.length > 0 ? active : qsTr("System default")
        var configuredLabel = configured.length > 0 ? configured : qsTr("System default")
        return active === configured
                ? activeLabel
                : qsTr("%1; restart to use %2").arg(activeLabel).arg(configuredLabel)
    }

    ScrollView {
        id: scroll
        objectName: "homeBoundedViewport"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            spacing: root.tokens.space24

            Item { Layout.preferredHeight: root.tokens.space8 }

            GridLayout {
                objectName: "homeBoundedHeader"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.leftMargin: root.tokens.space24
                Layout.rightMargin: root.tokens.space24
                columns: width >= root.tokens.metric(520) ? 2 : 1
                columnSpacing: root.tokens.space16
                rowSpacing: root.tokens.space8

                PlainText {
                    id: pageHeading
                    objectName: "homeBoundedHeading"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    text: qsTr("Home")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.pageHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                    Accessible.name: text
                }

                RowLayout {
                    objectName: "homeBoundedDictationControl"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.alignment: width >= root.tokens.metric(520) ? Qt.AlignRight : Qt.AlignLeft
                    spacing: root.tokens.space8

                    PlainText {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: root.value(root.appState, "enabled", true)
                              ? qsTr("Dictation on") : qsTr("Dictation off")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        font.weight: Font.DemiBold
                        wrapMode: Text.Wrap
                        Accessible.ignored: true
                    }
                    QuietSwitch {
                        objectName: "dictationSwitch"
                        tokens: root.tokens
                        checked: root.value(root.appState, "enabled", true)
                        accessibleName: qsTr("Dictation")
                        accessibleDescription: checked
                                               ? qsTr("Dictation is on")
                                               : qsTr("Dictation is off and the microphone stream is closed")
                        onToggled: bridge.toggleDictation()
                    }
                }
            }

            GlassSurface {
                id: readinessHero
                objectName: "homeBoundedReadinessHero"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.leftMargin: root.tokens.space24
                Layout.rightMargin: root.tokens.space24
                implicitHeight: heroContent.implicitHeight + padding * 2
                tokens: root.tokens
                role: "major"
                fillColor: root.statusIsError() ? root.tokens.dangerSurface
                                                : root.tokens.majorSurface
                edgeColor: root.statusIsError() ? root.tokens.danger : root.tokens.border

                ColumnLayout {
                    id: heroContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: root.tokens.space16

                    GridLayout {
                        Layout.minimumWidth: 0
                        Layout.fillWidth: true
                        columns: width >= root.tokens.metric(500) ? 2 : 1
                        columnSpacing: root.tokens.space16
                        rowSpacing: root.tokens.space12

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            spacing: root.tokens.space12

                            StatusOrb {
                                Layout.alignment: Qt.AlignTop
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                tokens: root.tokens
                                statusKind: root.statusKind()
                                label: root.statusText()
                                description: root.statusDetail()
                            }
                        }

                        QuietButton {
                            visible: root.value(root.appState, "availability", "") === "needs_attention"
                                     || root.value(root.appState, "pipeline", "") === "error"
                                     || root.issueAction().length > 0
                            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                            tokens: root.tokens
                            text: root.issueActionLabel()
                            kind: root.statusIsError() ? "danger" : "secondary"
                            accessibleDescription: qsTr("Perform the recommended recovery action")
                            onClicked: root.runIssueAction()
                        }
                    }

                    PlainText {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: root.statusDetail()
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                        Accessible.name: text
                    }

                    SignalPath {
                        objectName: "homeBoundedSignalPath"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.maximumWidth: root.tokens.metric(560)
                        tokens: root.tokens
                        activeStage: root.stage()
                    }
                }
            }

            GridLayout {
                objectName: "homeBoundedActionGrid"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.leftMargin: root.tokens.space24
                Layout.rightMargin: root.tokens.space24
                columns: width >= root.tokens.metric(680) ? 2 : 1
                columnSpacing: root.tokens.space16
                rowSpacing: root.tokens.space16

                GlassSurface {
                    objectName: "homeBoundedInstructionSurface"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    implicitHeight: instructionContent.implicitHeight + padding * 2
                    tokens: root.tokens
                    role: "content"
                    elevated: false

                    ColumnLayout {
                        id: instructionContent
                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: root.tokens.space8

                        PlainText {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: root.setting("toggle_mode", false)
                                  ? qsTr("Press %1 to start and stop").arg(root.displayHotkey())
                                  : qsTr("Hold %1, speak, then release").arg(root.displayHotkey())
                            color: root.tokens.text
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.sectionHeading
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                            Accessible.role: Accessible.Heading
                            Accessible.name: text
                        }

                        PlainText {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: qsTr("Speakr cleans up your words locally and inserts them at the cursor.")
                            color: root.tokens.mutedText
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.body
                            wrapMode: Text.Wrap
                        }
                    }
                }

                GlassSurface {
                    objectName: "homeBoundedActionSurface"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    implicitHeight: actionContent.implicitHeight + padding * 2
                    tokens: root.tokens
                    role: "notice"
                    elevated: false

                    ColumnLayout {
                        id: actionContent
                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: root.tokens.space12

                        PlainText {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: qsTr("Ready when you are")
                            color: root.tokens.text
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.statusHeading
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                            Accessible.role: Accessible.Heading
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: root.tokens.space12

                            QuietButton {
                                objectName: "homeBoundedShortcutButton"
                                tokens: root.tokens
                                text: bridge.capturingHotkey ? qsTr("Cancel shortcut capture") : qsTr("Change shortcut")
                                kind: bridge.capturingHotkey ? "danger" : "secondary"
                                accessibleDescription: bridge.capturingHotkey
                                                       ? qsTr("Stop waiting for a new shortcut")
                                                       : qsTr("Wait for the next key or key combination without a timeout")
                                onClicked: bridge.capturingHotkey
                                           ? bridge.cancelHotkeyCapture() : bridge.beginHotkeyCapture()
                            }

                            QuietButton {
                                objectName: "homeBoundedConfirmShortcutButton"
                                visible: bridge.capturingHotkey
                                         && String(root.value(root.appState, "pending_hotkey", "")).length > 0
                                tokens: root.tokens
                                text: qsTr("Use %1").arg(String(root.value(root.appState, "pending_hotkey", "")))
                                kind: "primary"
                                accessibleDescription: qsTr("Confirm the captured dictation shortcut")
                                onClicked: bridge.confirmHotkey()
                            }

                            QuietButton {
                                objectName: "homeBoundedPracticeButton"
                                tokens: root.tokens
                                text: qsTr("Start Practice")
                                kind: "primary"
                                accessibleDescription: qsTr("Open temporary practice dictation")
                                onClicked: root.navigateRequested("practice")
                            }
                        }

                        HotkeyWarning {
                            Layout.fillWidth: true
                            tokens: root.tokens
                            candidate: String(root.value(root.appState, "pending_hotkey", ""))
                        }
                    }
                }
            }

            ColumnLayout {
                objectName: "homeBoundedSummarySection"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.leftMargin: root.tokens.space24
                Layout.rightMargin: root.tokens.space24
                spacing: root.tokens.space12

                SectionHeading {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    tokens: root.tokens
                    title: qsTr("At a glance")
                    description: qsTr("The local path Speakr will use for your next dictation.")
                }

                GridLayout {
                    objectName: "homeBoundedSummaryGrid"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    columns: width >= root.tokens.metric(640) ? 2 : 1
                    columnSpacing: root.tokens.space12
                    rowSpacing: root.tokens.space12

                    Repeater {
                        objectName: "summaryRepeater"
                        model: [
                            { label: qsTr("Microphone"), value: root.microphoneSummary(), symbol: "M" },
                            { label: qsTr("Speech model"), value: String(root.value(root.appState, "model", root.setting("model", "auto"))) === "auto" ? qsTr("Automatic") : String(root.value(root.appState, "model", root.setting("model", "auto"))), symbol: "S" },
                            { label: qsTr("Text cleanup"), value: root.value(root.appState, "cleanup_path", "rules") === "ollama" ? qsTr("Local model cleanup available") : qsTr("Basic cleanup active"), symbol: "C" },
                            { label: qsTr("Privacy"), value: !root.value(root.appState, "enabled", true)
                                                             ? qsTr("Microphone closed; rolling audio cleared")
                                                             : (root.setting("keep_mic_stream_open", true)
                                                                ? (root.setting("microphone_stream_open", false)
                                                                   ? qsTr("%1 seconds held only in RAM").arg(root.setting("preroll_seconds", 0.4))
                                                                   : qsTr("Microphone not ready; no rolling audio held"))
                                                                : qsTr("Microphone opens only while dictating")), symbol: "P" }
                        ]

                        delegate: GlassSurface {
                            id: summaryCard
                            objectName: "homeBoundedSummaryCard"
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            implicitHeight: summaryContent.implicitHeight + padding * 2
                            tokens: root.tokens
                            role: "content"
                            elevated: false

                            RowLayout {
                                id: summaryContent
                                anchors.left: parent.left
                                anchors.right: parent.right
                                Layout.minimumWidth: 0
                                spacing: root.tokens.space12

                                Rectangle {
                                    objectName: "homeSummarySymbolSurface"
                                    readonly property color edgeColor:
                                        root.tokens.highContrast
                                        ? root.tokens.accentText
                                        : root.tokens.accent
                                    Layout.preferredWidth: root.tokens.controlHeight
                                    Layout.preferredHeight: Layout.preferredWidth
                                    radius: root.tokens.radiusControl
                                    color: root.tokens.highContrast
                                           ? root.tokens.accent : root.tokens.hover
                                    border.width: root.tokens.borderWidth
                                    border.color: edgeColor
                                    Accessible.ignored: true

                                    PlainText {
                                        objectName: "homeSummarySymbolGlyph"
                                        anchors.centerIn: parent
                                        text: summaryCard.modelData.symbol
                                        color: root.tokens.highContrast
                                               ? root.tokens.accentText : root.tokens.accent
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.statusHeading
                                        font.weight: Font.Bold
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    spacing: root.tokens.space4

                                    PlainText {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        text: summaryCard.modelData.label
                                        color: root.tokens.text
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.body
                                        font.weight: Font.DemiBold
                                        wrapMode: Text.Wrap
                                    }
                                    PlainText {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        text: summaryCard.modelData.value
                                        color: root.tokens.mutedText
                                        font.family: root.tokens.fontFamily
                                        font.pixelSize: root.tokens.secondary
                                        wrapMode: Text.Wrap
                                    }
                                }
                            }
                        }
                    }
                }
            }

            InlineNotice {
                objectName: "homeBoundedPrivacyNotice"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.leftMargin: root.tokens.space24
                Layout.rightMargin: root.tokens.space24
                tokens: root.tokens
                kind: "success"
                title: qsTr("Private by design")
                message: qsTr("Audio and dictated text stay on this device. Speakr keeps no transcript history.")
            }

            PlainText {
                objectName: "homeBoundedLatestOutcome"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.leftMargin: root.tokens.space24
                Layout.rightMargin: root.tokens.space24
                text: qsTr("Latest outcome: %1").arg(root.value(root.appState, "latest_outcome", qsTr("Ready for dictation")))
                color: root.tokens.mutedText
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.secondary
                wrapMode: Text.Wrap
                Accessible.name: text
            }

            Item { Layout.preferredHeight: root.tokens.space24 }
        }
    }
}
