import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var tokens
    property var settings: ({})
    property var appState: ({})
    property string selectedCategory: qsTr("All")
    property var lastChange: null
    property var pendingSensitiveChange: null
    property string saveError: ""

    function focusHeading() {
        pageHeading.forceActiveFocus(Qt.OtherFocusReason)
    }

    readonly property var categories: [
        qsTr("All"),
        qsTr("Dictation"),
        qsTr("Microphone & Language"),
        qsTr("Accuracy"),
        qsTr("Text Cleanup"),
        qsTr("Per-App Behavior"),
        qsTr("Privacy"),
        qsTr("Accessibility"),
        qsTr("Advanced")
    ]

    readonly property var rows: [
        { category: qsTr("Dictation"), label: qsTr("Shortcut"), description: qsTr("Hold or press this shortcut to dictate. Capture has no timeout; Escape cancels."), keywords: "hotkey key", path: "hotkey", type: "hotkey", fallback: "right ctrl" },
        { category: qsTr("Dictation"), label: qsTr("Shortcut behavior"), description: qsTr("Hold records until release. Toggle uses one press to start and another to stop."), keywords: "hold toggle", path: "toggle_mode", type: "combo", options: [qsTr("Hold to speak"), qsTr("Press to start and stop")], values: [false, true], fallback: false },
        { category: qsTr("Dictation"), label: qsTr("Spoken layout commands"), description: qsTr("Recognize phrases such as new line, new paragraph, and bullet point."), keywords: "voice commands layout", path: "voice_commands", type: "switch", fallback: true },
        { category: qsTr("Dictation"), label: qsTr("Edit Mode"), description: qsTr("When text is selected, treat dictation as an instruction and leave the original unchanged if editing fails."), keywords: "selection transform", path: "edit_mode.enabled", type: "switch", fallback: true },
        { category: qsTr("Dictation"), label: qsTr("Open window when Speakr starts"), description: qsTr("Turn this off for tray-first use. Relaunching Speakr while it is already running still opens the window."), keywords: "startup tray launch", path: "ui.open_window_on_start", type: "switch", fallback: true },

        { category: qsTr("Microphone & Language"), label: qsTr("Input device"), description: qsTr("Leave blank to use the operating system default microphone. Changing this requires restarting Speakr."), keywords: "audio mic restart", path: "input_device", type: "text", allowEmpty: true, fallback: "" },
        { category: qsTr("Microphone & Language"), label: qsTr("Language"), description: qsTr("Automatic detection is best for multilingual use. A fixed language can improve consistency."), keywords: "locale speech", path: "language", type: "combo", options: [qsTr("Automatic"), "English", "Spanish", "French", "German", "Italian", "Portuguese"], values: [null, "en", "es", "fr", "de", "it", "pt"], fallback: null },
        { category: qsTr("Microphone & Language"), label: qsTr("Microphone sample rate"), description: qsTr("Samples per second used by the local recorder. Changing this requires restarting Speakr."), keywords: "hz audio restart", path: "sample_rate", type: "number", fallback: 16000 },

        { category: qsTr("Accuracy"), label: qsTr("Speech model"), description: qsTr("Automatic selects an appropriate local model for the available hardware. Applying can require a local model load."), keywords: "whisper model size", path: "model", type: "confirm_combo", options: [qsTr("Automatic"), "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"], values: ["auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"], fallback: "auto" },
        { category: qsTr("Accuracy"), label: qsTr("Beam size"), description: qsTr("Higher values can improve local transcription at the cost of processing time."), keywords: "decoding", path: "beam_size", type: "combo", options: [qsTr("Automatic"), "1", "3", "5"], values: ["auto", 1, 3, 5], fallback: "auto" },
        { category: qsTr("Accuracy"), label: qsTr("Sound detection threshold"), description: qsTr("Lower values hear quieter speech; higher values reject more background noise."), keywords: "vad voice quiet", path: "vad_threshold", type: "number", fallback: 0.35 },
        { category: qsTr("Accuracy"), label: qsTr("Learn recurring words"), description: qsTr("Keep notable recurring words in a local vocabulary file."), keywords: "learning dictionary", path: "learning.enabled", type: "switch", fallback: true },
        { category: qsTr("Accuracy"), label: qsTr("Occurrences before learning"), description: qsTr("How many local appearances are required before a word becomes a hint."), keywords: "threshold vocabulary", path: "learning.min_occurrences", type: "number", fallback: 3 },

        { category: qsTr("Text Cleanup"), label: qsTr("Clean up dictated text"), description: qsTr("Remove filler, normalize spacing, and apply spoken layout commands locally."), keywords: "formatting filler", path: "formatting.enabled", type: "switch", fallback: true },
        { category: qsTr("Text Cleanup"), label: qsTr("Use local Ollama when available"), description: qsTr("Apply optional local model polish. Basic cleanup remains available when Ollama is off or unavailable."), keywords: "llm polish", path: "formatting.use_ollama", type: "switch", fallback: true },
        { category: qsTr("Text Cleanup"), label: qsTr("Start local Ollama automatically"), description: qsTr("Start the user's local Ollama process when cleanup needs it."), keywords: "serve model", path: "formatting.autostart_ollama", type: "switch", fallback: true },
        { category: qsTr("Text Cleanup"), label: qsTr("Local Ollama model"), description: qsTr("Exact local model name used for optional cleanup."), keywords: "llama", path: "formatting.ollama_model", type: "text", fallback: "llama3.1:8b" },

        { category: qsTr("Per-App Behavior"), label: qsTr("Per-app tones and exclusions"), description: qsTr("Open the local configuration file to manage exact application names and casual, formal, neutral, or literal behavior."), keywords: "apps excluded tone literal", path: "", type: "action", actionText: qsTr("Open local config"), actionKind: "config" },

        { category: qsTr("Privacy"), label: qsTr("Keep microphone ready"), description: qsTr("Keep the local microphone stream open for lower latency. Turning Dictation off always closes it."), keywords: "stream mic indicator", path: "keep_mic_stream_open", type: "switch", fallback: true },
        { category: qsTr("Privacy"), label: qsTr("Rolling RAM audio"), description: qsTr("Seconds held only in RAM and continuously replaced so the first word is not clipped."), keywords: "preroll memory audio", path: "preroll_seconds", type: "number", fallback: 0.4 },
        { category: qsTr("Privacy"), label: qsTr("Screen context"), description: qsTr("Read focused text locally once per dictation to improve spelling. It is held only for that dictation."), keywords: "window spelling local", path: "screen_context.enabled", type: "switch", fallback: true },
        { category: qsTr("Privacy"), label: qsTr("Recent in-memory cleanup context"), description: qsTr("Keep a few recent dictations in memory for local cleanup continuity; never write them as history."), keywords: "recent transcript", path: "formatting.include_recent_context", type: "switch", fallback: true },
        { category: qsTr("Privacy"), label: qsTr("Transcript logging"), description: qsTr("Write dictated text to the local Speakr log. Off is the privacy-preserving default."), keywords: "file history log", path: "log_transcripts", type: "switch", fallback: false },
        { category: qsTr("Privacy"), label: qsTr("Restore clipboard"), description: qsTr("Restore clipboard contents after paste-based insertion."), keywords: "paste", path: "restore_clipboard", type: "switch", fallback: true },

        { category: qsTr("Accessibility"), label: qsTr("Theme"), description: qsTr("Follow the operating system or choose a fixed interface theme."), keywords: "light dark contrast", path: "ui.theme", type: "combo", options: [qsTr("System"), qsTr("Light"), qsTr("Dark"), qsTr("High contrast")], values: ["system", "light", "dark", "high_contrast"], fallback: "system" },
        { category: qsTr("Accessibility"), label: qsTr("Control spacing"), description: qsTr("Comfortable is recommended. Compact reduces unused space while preserving 44-pixel targets."), keywords: "density compact comfortable", path: "ui.density", type: "combo", options: [qsTr("Comfortable"), qsTr("Compact")], values: ["comfortable", "compact"], fallback: "comfortable" },
        { category: qsTr("Accessibility"), label: qsTr("Text size"), description: qsTr("System follows operating-system scaling. Larger choices reflow controls without hiding labels."), keywords: "font zoom vision", path: "ui.text_scale", type: "combo", options: [qsTr("System"), "110%", "125%", "150%", "175%", "200%"], values: ["system", 110, 125, 150, 175, 200], fallback: "system" },
        { category: qsTr("Accessibility"), label: qsTr("Motion"), description: qsTr("Reduced motion removes translation, drawing, and connector animations while preserving reading time."), keywords: "animation reduce", path: "ui.reduced_motion", type: "combo", options: [qsTr("System"), qsTr("Reduced")], values: ["system", "reduce"], fallback: "system" },
        { category: qsTr("Accessibility"), label: qsTr("HUD visibility"), description: qsTr("Show the non-interactive status HUD while dictating, always, or never."), keywords: "overlay", path: "ui.hud_visibility", type: "combo", options: [qsTr("While dictating"), qsTr("Always"), qsTr("Off")], values: ["while_dictating", "always", "off"], fallback: "while_dictating" },
        { category: qsTr("Accessibility"), label: qsTr("HUD size"), description: qsTr("Use a standard or large status HUD."), keywords: "overlay vision", path: "ui.hud_size", type: "combo", options: [qsTr("Standard"), qsTr("Large")], values: ["standard", "large"], fallback: "standard" },
        { category: qsTr("Accessibility"), label: qsTr("HUD text scale"), description: qsTr("Scale the status HUD independently without changing the main window."), keywords: "overlay zoom vision", path: "ui.hud_scale", type: "combo", options: ["100%", "125%", "150%", "175%", "200%"], values: [100, 125, 150, 175, 200], fallback: 100 },
        { category: qsTr("Accessibility"), label: qsTr("HUD position"), description: qsTr("Place the HUD at the bottom or top of the active monitor."), keywords: "edge screen", path: "ui.hud_edge", type: "combo", options: [qsTr("Bottom"), qsTr("Top")], values: ["bottom", "top"], fallback: "bottom" },
        { category: qsTr("Accessibility"), label: qsTr("Background announcements"), description: qsTr("Announce only Listening, Processing locally, and the final result. Off avoids screen-reader audio entering the microphone."), keywords: "screen reader voiceover nvda", path: "ui.background_announcements", type: "switch", fallback: false },

        { category: qsTr("Advanced"), label: qsTr("Processing device"), description: qsTr("Automatic tries the local GPU and safely falls back to CPU."), keywords: "cuda gpu cpu", path: "device", type: "confirm_combo", options: [qsTr("Automatic"), "CPU", "CUDA"], values: ["auto", "cpu", "cuda"], fallback: "auto" },
        { category: qsTr("Advanced"), label: qsTr("Compute type"), description: qsTr("Numeric format used by faster-whisper on this device."), keywords: "float int8", path: "compute_type", type: "confirm_combo", options: [qsTr("Automatic"), "float16", "float32", "int8", "int8_float16"], values: ["auto", "float16", "float32", "int8", "int8_float16"], fallback: "auto" },
        { category: qsTr("Advanced"), label: qsTr("Streaming transcription"), description: qsTr("Process long dictations in local chunks at natural pauses."), keywords: "chunks long", path: "streaming.enabled", type: "switch", fallback: true },
        { category: qsTr("Advanced"), label: qsTr("Streaming chunk length"), description: qsTr("Seconds per local transcription chunk."), keywords: "duration", path: "streaming.chunk_seconds", type: "number", fallback: 10 },
        { category: qsTr("Advanced"), label: qsTr("Minimum dictation length"), description: qsTr("Shorter presses are ignored as accidental taps."), keywords: "seconds duration", path: "min_duration_seconds", type: "number", fallback: 0.3 },
        { category: qsTr("Advanced"), label: qsTr("Maximum dictation length"), description: qsTr("Maximum seconds for one local recording."), keywords: "seconds duration", path: "max_duration_seconds", type: "number", fallback: 120 },
        { category: qsTr("Advanced"), label: qsTr("Text insertion"), description: qsTr("Paste is most compatible; simulated typing avoids using the clipboard."), keywords: "clipboard type", path: "injection", type: "combo", options: [qsTr("Paste"), qsTr("Simulated typing")], values: ["paste", "type"], fallback: "paste" },
        { category: qsTr("Advanced"), label: qsTr("Local Ollama address"), description: qsTr("Loopback address for the user's local Ollama process. Remote addresses are rejected."), keywords: "url 127 localhost", path: "formatting.ollama_url", type: "text", fallback: "http://127.0.0.1:11434" },
        { category: qsTr("Advanced"), label: qsTr("Ollama timeout"), description: qsTr("Seconds before optional local cleanup falls back to basic cleanup."), keywords: "fallback", path: "formatting.timeout_seconds", type: "number", fallback: 15 },
        { category: qsTr("Advanced"), label: qsTr("Ollama keep-alive"), description: qsTr("How long the local model remains loaded after dictation."), keywords: "memory vram", path: "formatting.keep_alive", type: "text", fallback: "10m" },
        { category: qsTr("Advanced"), label: qsTr("Raw configuration"), description: qsTr("Open the local configuration file for exact values not shown here."), keywords: "json expert", path: "", type: "action", actionText: qsTr("Open local config"), actionKind: "config" }
    ]

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

    function matches(row) {
        var categoryMatch = selectedCategory === qsTr("All") || row.category === selectedCategory
        var query = searchField.text.trim().toLowerCase()
        if (query.length === 0) return categoryMatch
        var haystack = (row.category + " " + row.label + " " + row.description + " " + row.keywords).toLowerCase()
        return categoryMatch && haystack.indexOf(query) >= 0
    }

    function resultCount() {
        var count = 0
        for (var i = 0; i < rows.length; ++i) {
            if (matches(rows[i])) ++count
        }
        return count
    }

    function toneSummary() {
        var source = setting("app_tones", ({})) || ({})
        var entries = []
        for (var key in source) {
            if (source.hasOwnProperty === undefined || source.hasOwnProperty(key))
                entries.push(String(key) + ": " + String(source[key]))
        }
        entries.sort()
        return entries.length > 0 ? entries.join("  •  ") : qsTr("None configured")
    }

    function excludedAppsSummary() {
        var source = setting("hotkey_exclude_apps", []) || []
        if (source.length !== undefined)
            return source.length > 0 ? Array.prototype.join.call(source, ", ") : qsTr("None configured")
        return String(source)
    }

    function commitChange(path, value, previousValue) {
        if (!Boolean(bridge.setSetting(path, value))) {
            saveError = qsTr("That setting could not be saved. The previous value is still active.")
            lastChange = null
            return false
        }
        lastChange = { path: path, previous: previousValue }
        saveError = ""
        savedTimer.restart()
        return true
    }

    function applyChange(path, value, previousValue) {
        if (path === "log_transcripts" && Boolean(value)) {
            pendingSensitiveChange = { path: path, value: value, previous: previousValue }
            Qt.callLater(function() { transcriptCancel.forceActiveFocus(Qt.TabFocusReason) })
            return
        }
        commitChange(path, value, previousValue)
    }

    Timer {
        id: savedTimer
        interval: 8000
        repeat: false
        onTriggered: root.lastChange = null
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
                spacing: root.tokens.space12

                PlainText {
                    id: pageHeading
                    Layout.fillWidth: true
                    text: qsTr("Settings")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.pageHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                    Accessible.name: text
                }

                QuietTextField {
                    id: searchField
                    Layout.fillWidth: true
                    tokens: root.tokens
                    placeholderText: qsTr("Search settings")
                    accessibleName: qsTr("Search settings")
                    accessibleDescription: qsTr("Search setting labels and descriptions within the selected category")
                }

                PlainText {
                    Layout.fillWidth: true
                    text: qsTr("%1 settings found").arg(root.resultCount())
                    color: root.tokens.mutedText
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.secondary
                    Accessible.name: text
                }
            }

            Flow {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: root.tokens.space8
                Accessible.role: Accessible.PageTabList
                Accessible.name: qsTr("Settings categories")

                Repeater {
                    model: root.categories

                    delegate: NavigationButton {
                        required property string modelData
                        tokens: root.tokens
                        text: modelData
                        selected: root.selectedCategory === modelData
                        onClicked: root.selectedCategory = modelData
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                visible: root.lastChange !== null
                implicitHeight: savedRow.implicitHeight + root.tokens.space16
                radius: root.tokens.radius
                color: root.tokens.successSurface
                border.width: 1
                border.color: root.tokens.success
                Accessible.role: Accessible.AlertMessage
                Accessible.name: qsTr("Saved. Undo is available.")

                RowLayout {
                    id: savedRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: root.tokens.space8
                    spacing: root.tokens.space12

                    PlainText {
                        Layout.fillWidth: true
                        text: qsTr("Saved")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        font.weight: Font.DemiBold
                    }

                    QuietButton {
                        tokens: root.tokens
                        text: qsTr("Undo")
                        enabled: root.lastChange !== null
                        accessibleDescription: qsTr("Restore the previous value for the most recent setting")
                        onClicked: {
                            if (root.lastChange !== null) {
                                if (Boolean(bridge.setSetting(root.lastChange.path, root.lastChange.previous))) {
                                    root.lastChange = null
                                    root.saveError = ""
                                } else {
                                    root.saveError = qsTr("Undo could not be saved. The current value is still active.")
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
                visible: root.pendingSensitiveChange !== null
                implicitHeight: transcriptWarning.implicitHeight + root.tokens.space24
                radius: root.tokens.radius
                color: root.tokens.warningSurface
                border.width: 1
                border.color: root.tokens.warning
                Accessible.role: Accessible.AlertMessage
                Accessible.name: qsTr("Confirm transcript logging")

                ColumnLayout {
                    id: transcriptWarning
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: root.tokens.space12
                    spacing: root.tokens.space8

                    PlainText {
                        Layout.fillWidth: true
                        text: qsTr("Confirm transcript logging")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.statusHeading
                        font.weight: Font.DemiBold
                        wrapMode: Text.Wrap
                        Accessible.role: Accessible.Heading
                    }

                    PlainText {
                        Layout.fillWidth: true
                        text: qsTr("This writes dictated text to %1 on this device. Practice text is never logged. Turn this on only if you want a persistent local transcript record.")
                              .arg(String(root.setting("log_path", "speakr.log")))
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: root.tokens.space8

                        QuietButton {
                            id: transcriptCancel
                            tokens: root.tokens
                            text: qsTr("Cancel")
                            kind: "primary"
                            accessibleDescription: qsTr("Keep transcript logging off")
                            onClicked: root.pendingSensitiveChange = null
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Enable local logging")
                            kind: "danger"
                            accessibleDescription: qsTr("Begin writing dictated text to the displayed local log path")
                            onClicked: {
                                var change = root.pendingSensitiveChange
                                root.pendingSensitiveChange = null
                                if (change !== null)
                                    root.commitChange(change.path, change.value, change.previous)
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                visible: root.saveError.length > 0
                implicitHeight: saveErrorText.implicitHeight + root.tokens.space24
                radius: root.tokens.radius
                color: root.tokens.dangerSurface
                border.width: 1
                border.color: root.tokens.danger
                Accessible.role: Accessible.AlertMessage
                Accessible.name: root.saveError

                PlainText {
                    id: saveErrorText
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: root.tokens.space12
                    text: root.saveError
                    color: root.tokens.danger
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    wrapMode: Text.Wrap
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: 0

                Repeater {
                    model: root.rows

                    delegate: SettingRow {
                        required property var modelData
                        Layout.fillWidth: true
                        visible: root.matches(modelData)
                        Layout.preferredHeight: visible ? implicitHeight : 0
                        tokens: root.tokens
                        label: modelData.label
                        description: modelData.description
                        category: modelData.category
                        path: modelData.path
                        controlType: modelData.type
                        options: modelData.options || []
                        values: modelData.values || []
                        currentValue: modelData.type === "hotkey"
                                      ? (root.appState.hotkey || root.setting(modelData.path, modelData.fallback))
                                      : root.setting(modelData.path, modelData.fallback)
                        showCategory: root.selectedCategory === qsTr("All") || searchField.text.trim().length > 0
                        capturingHotkey: bridge.capturingHotkey
                        pendingHotkey: String(root.appState.pending_hotkey || "")
                        actionText: modelData.actionText || qsTr("Open")
                        actionKind: modelData.actionKind || "config"
                        allowEmpty: Boolean(modelData.allowEmpty || false)
                        onChangeRequested: function(path, value, previousValue) {
                            root.applyChange(path, value, previousValue)
                        }
                        onActionRequested: function(kind) { bridge.openLocal(kind) }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: root.tokens.space24
                    visible: root.selectedCategory === qsTr("Advanced")
                             && searchField.text.trim().length === 0
                    implicitHeight: localValues.implicitHeight + root.tokens.space24
                    radius: root.tokens.radius
                    color: root.tokens.surfaceRaised
                    border.width: 1
                    border.color: root.tokens.border
                    Accessible.role: Accessible.Grouping
                    Accessible.name: qsTr("Exact per-app values")

                    ColumnLayout {
                        id: localValues
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: root.tokens.space12
                        spacing: root.tokens.space8

                        PlainText {
                            Layout.fillWidth: true
                            text: qsTr("Exact per-app values")
                            color: root.tokens.text
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.statusHeading
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                            Accessible.role: Accessible.Heading
                        }

                        PlainText {
                            Layout.fillWidth: true
                            text: qsTr("Tones: %1").arg(root.toneSummary())
                            color: root.tokens.text
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.secondary
                            wrapMode: Text.Wrap
                            Accessible.name: text
                        }

                        PlainText {
                            Layout.fillWidth: true
                            text: qsTr("Shortcut exclusions: %1").arg(root.excludedAppsSummary())
                            color: root.tokens.text
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.secondary
                            wrapMode: Text.Wrap
                            Accessible.name: text
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Open local config")
                            accessibleDescription: qsTr("Open the exact local per-app tone and shortcut exclusion values")
                            onClicked: bridge.openLocal("config")
                        }
                    }
                }

                PlainText {
                    Layout.fillWidth: true
                    Layout.topMargin: root.tokens.space24
                    visible: root.resultCount() === 0
                    text: qsTr("No settings match. Try a broader term or choose All.")
                    color: root.tokens.mutedText
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                    Accessible.role: Accessible.Note
                    Accessible.name: text
                }
            }

            Item { Layout.preferredHeight: root.tokens.space24 }
        }
    }
}
