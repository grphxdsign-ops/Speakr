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
        if (custom.length > 0)
            return custom
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
        if (statusCode === "no_speech")
            return qsTr("Try again when you are ready.")
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

    function statusGlyph() {
        if (statusIsError()) return "!"
        if (statusIsWarning()) return "i"
        if (!value(appState, "enabled", true)) return "○"
        if (value(appState, "capture", "idle") === "listening") return "●"
        var pipeline = value(appState, "pipeline", "idle")
        if (pipeline === "success" || (pipeline === "idle"
                                      && value(appState, "availability", "starting") === "ready"))
            return "✓"
        return "…"
    }

    function statusColor() {
        if (statusIsError()) return tokens.danger
        if (statusIsWarning()) return tokens.warning
        var pipeline = value(appState, "pipeline", "idle")
        if (pipeline === "success" || (pipeline === "idle"
                                      && value(appState, "availability", "starting") === "ready"
                                      && value(appState, "enabled", true)))
            return tokens.success
        return tokens.accent
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
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            spacing: root.tokens.space24

            Item { Layout.preferredHeight: root.tokens.space8 }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: root.tokens.space16

                Text {
                    id: pageHeading
                    Layout.fillWidth: true
                    text: qsTr("Home")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.pageHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                    Accessible.name: text
                }

                QuietSwitch {
                    tokens: root.tokens
                    checked: root.value(root.appState, "enabled", true)
                    accessibleName: qsTr("Dictation")
                    accessibleDescription: checked
                                           ? qsTr("Dictation is on")
                                           : qsTr("Dictation is off and the microphone stream is closed")
                    onToggled: bridge.toggleDictation()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                implicitHeight: statusContent.implicitHeight + root.tokens.space32
                radius: root.tokens.radiusLarge
                color: root.statusIsError()
                       ? root.tokens.dangerSurface : root.tokens.surface
                border.width: 1
                border.color: root.statusIsError()
                              ? root.tokens.danger : root.tokens.border

                ColumnLayout {
                    id: statusContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: root.tokens.space16
                    spacing: root.tokens.space12

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: root.tokens.space12

                        Rectangle {
                            Layout.alignment: Qt.AlignTop
                            implicitWidth: root.tokens.metric(28)
                            implicitHeight: implicitWidth
                            Layout.preferredWidth: implicitWidth
                            Layout.preferredHeight: implicitHeight
                            radius: width / 2
                            color: root.statusColor()
                            Accessible.ignored: true

                            Text {
                                anchors.centerIn: parent
                                text: root.statusGlyph()
                                color: root.tokens.highContrast
                                       && (root.statusIsError() || root.statusIsWarning())
                                       ? root.tokens.background : root.tokens.accentText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.statusHeading
                                font.weight: Font.Bold
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: root.tokens.space4

                            Text {
                                Layout.fillWidth: true
                                text: root.statusText()
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.statusHeading
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                                Accessible.role: Accessible.Heading
                                Accessible.name: text
                            }

                            Text {
                                Layout.fillWidth: true
                                text: root.statusDetail()
                                color: root.tokens.mutedText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.secondary
                                wrapMode: Text.Wrap
                            }
                        }

                        QuietButton {
                            visible: root.value(root.appState, "availability", "") === "needs_attention"
                                     || root.value(root.appState, "pipeline", "") === "error"
                                     || root.issueAction().length > 0
                            tokens: root.tokens
                            text: root.issueActionLabel()
                            accessibleDescription: qsTr("Perform the recommended recovery action")
                            onClicked: root.runIssueAction()
                        }
                    }

                    SignalPath {
                        Layout.fillWidth: true
                        Layout.maximumWidth: root.tokens.metric(520)
                        tokens: root.tokens
                        activeStage: root.stage()
                    }
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                columns: width >= root.tokens.metric(760) ? 2 : 1
                columnSpacing: root.tokens.space16
                rowSpacing: root.tokens.space12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.tokens.space8

                    Text {
                        Layout.fillWidth: true
                        text: root.setting("toggle_mode", false)
                              ? qsTr("Press %1 to start and stop").arg(root.displayHotkey())
                              : qsTr("Hold %1, speak, then release").arg(root.displayHotkey())
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.sectionHeading
                        font.weight: Font.DemiBold
                        wrapMode: Text.Wrap
                        Accessible.role: Accessible.Heading
                    }

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Speakr cleans up your words locally and inserts them at the cursor.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: root.tokens.space8

                    Flow {
                        Layout.fillWidth: true
                        spacing: root.tokens.space12

                        QuietButton {
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
                            visible: bridge.capturingHotkey
                                     && String(root.value(root.appState, "pending_hotkey", "")).length > 0
                            tokens: root.tokens
                            text: qsTr("Use %1").arg(String(root.value(root.appState, "pending_hotkey", "")))
                            kind: "primary"
                            accessibleDescription: qsTr("Confirm the captured dictation shortcut")
                            onClicked: bridge.confirmHotkey()
                        }

                        QuietButton {
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

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: 0

                Text {
                    Layout.fillWidth: true
                    Layout.bottomMargin: root.tokens.space12
                    text: qsTr("At a glance")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.sectionHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                }

                Repeater {
                    model: [
                        { label: qsTr("Microphone"), value: root.microphoneSummary() },
                        { label: qsTr("Speech model"), value: String(root.value(root.appState, "model", root.setting("model", "auto"))) === "auto" ? qsTr("Automatic") : String(root.value(root.appState, "model", root.setting("model", "auto"))) },
                        { label: qsTr("Text cleanup"), value: root.value(root.appState, "cleanup_path", "rules") === "ollama" ? qsTr("Local model cleanup available") : qsTr("Basic cleanup active") },
                        { label: qsTr("Privacy"), value: !root.value(root.appState, "enabled", true)
                                                         ? qsTr("Microphone closed; rolling audio cleared")
                                                         : (root.setting("keep_mic_stream_open", true)
                                                            ? (root.setting("microphone_stream_open", false)
                                                               ? qsTr("%1 seconds held only in RAM").arg(root.setting("preroll_seconds", 0.4))
                                                               : qsTr("Microphone not ready; no rolling audio held"))
                                                            : qsTr("Microphone opens only while dictating")) }
                    ]

                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: rowContent.implicitHeight + root.tokens.space24
                        color: "transparent"
                        border.width: 0

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            height: 1
                            color: root.tokens.border
                        }

                        GridLayout {
                            id: rowContent
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            columns: width >= root.tokens.metric(500) ? 2 : 1
                            columnSpacing: root.tokens.space24
                            rowSpacing: root.tokens.space4

                            Text {
                                Layout.fillWidth: true
                                text: modelData.label
                                color: root.tokens.text
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                font.weight: Font.Medium
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.value
                                color: root.tokens.mutedText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.body
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
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
