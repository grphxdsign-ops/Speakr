import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: root
    objectName: "settingsPage"

    required property var tokens
    property var settings: ({})
    property var appState: ({})
    property string selectedCategory: qsTr("All")
    property var lastChange: null
    property var pendingSensitiveChange: null
    property string saveError: ""
    property int rejectedChangeGeneration: 0
    property int focusScrollGeneration: 0
    readonly property int visibleResultCount: resultCount()

    function focusHeading() {
        pageHeading.forceActiveFocus(Qt.OtherFocusReason)
    }

    function isPageDescendant(item) {
        var current = item
        while (current !== null && current !== undefined) {
            if (current === root) return true
            current = current.parent
        }
        return false
    }

    function ensureFocusedItemVisible(item) {
        if (!isPageDescendant(item)) return
        var viewport = scroll.contentItem
        if (viewport === null || viewport === undefined
                || viewport.contentY === undefined) return
        var mapped = item.mapToItem(viewport, 0, 0)
        var margin = root.tokens.space12
        var top = Number(mapped.y)
        var bottom = top + Number(item.height)
        var viewportHeight = Number(viewport.height)
        var originY = Number(viewport.originY || 0)
        var contentHeight = Math.max(viewportHeight, Number(viewport.contentHeight || 0))
        var maximumY = originY + Math.max(0, contentHeight - viewportHeight)
        var nextY = Number(viewport.contentY)
        if (top < margin)
            nextY += top - margin
        else if (bottom > viewportHeight - margin)
            nextY += bottom - viewportHeight + margin
        viewport.contentY = Math.max(originY, Math.min(maximumY, nextY))
    }

    function queueFocusedItemVisibility(item) {
        focusScrollGeneration += 1
        var generation = focusScrollGeneration
        Qt.callLater(function() {
            if (generation !== root.focusScrollGeneration) return
            root.ensureFocusedItemVisible(item)
            Qt.callLater(function() {
                if (generation === root.focusScrollGeneration)
                    root.ensureFocusedItemVisible(item)
            })
        })
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

    readonly property var rows: root.baseRows.concat(root.perAppRows())
    readonly property var baseRows: [
        { category: qsTr("Dictation"), label: qsTr("Shortcut"), description: qsTr("Press one key to choose the dictation shortcut. Capture has no timeout; Cancel or Escape stops it."), keywords: "hotkey key", path: "hotkey", type: "hotkey", fallback: "right ctrl" },
        { category: qsTr("Dictation"), label: qsTr("Shortcut behavior"), description: qsTr("Hold records until release. Toggle uses one press to start and another to stop."), keywords: "hold toggle", path: "toggle_mode", type: "combo", options: [qsTr("Hold to speak"), qsTr("Press to start and stop")], values: [false, true], fallback: false },
        { category: qsTr("Dictation"), label: qsTr("Spoken layout commands"), description: qsTr("Recognize phrases such as new line, new paragraph, and bullet point."), keywords: "voice commands layout", path: "voice_commands", type: "switch", fallback: true },
        { category: qsTr("Dictation"), label: qsTr("Edit Mode"), description: qsTr("When text is selected, treat dictation as an instruction and leave the original unchanged if editing fails."), keywords: "selection transform", path: "edit_mode.enabled", type: "switch", fallback: true },
        { category: qsTr("Dictation"), label: qsTr("Open window when Speakr starts"), description: qsTr("Turn this off for tray-first use. Relaunching Speakr while it is already running still opens the window."), keywords: "startup tray launch", path: "ui.open_window_on_start", type: "switch", fallback: true },

        { category: qsTr("Microphone & Language"), label: qsTr("Input device"), description: qsTr("Leave blank to use the operating system default microphone. Changing this requires restarting Speakr."), keywords: "audio mic restart", path: "input_device", type: "text", allowEmpty: true, fallback: "" },
        { category: qsTr("Microphone & Language"), label: qsTr("Language"), description: qsTr("Automatic detection is best for multilingual use. A fixed language can improve consistency."), keywords: "locale speech", path: "language", type: "combo", options: [qsTr("Automatic"), "English", "Spanish", "French", "German", "Italian", "Portuguese"], values: [null, "en", "es", "fr", "de", "it", "pt"], fallback: null },
        { category: qsTr("Microphone & Language"), advanced: true, label: qsTr("Microphone sample rate"), description: qsTr("Samples per second used by the local recorder. Changing this requires restarting Speakr."), keywords: "hz audio restart", path: "sample_rate", type: "number", fallback: 16000 },

        { category: qsTr("Accuracy"), advanced: true, label: qsTr("Speech model"), description: qsTr("Automatic selects an appropriate local model for the available hardware. Applying can require a local model load."), keywords: "whisper model size", path: "model", type: "confirm_combo", options: [qsTr("Automatic"), "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"], values: ["auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"], fallback: "auto" },
        { category: qsTr("Accuracy"), advanced: true, label: qsTr("Beam size"), description: qsTr("Higher values can improve local transcription at the cost of processing time."), keywords: "decoding", path: "beam_size", type: "combo", options: [qsTr("Automatic"), "1", "3", "5"], values: ["auto", 1, 3, 5], fallback: "auto" },
        { category: qsTr("Accuracy"), advanced: true, label: qsTr("Sound detection threshold"), description: qsTr("Lower values hear quieter speech; higher values reject more background noise."), keywords: "vad voice quiet", path: "vad_threshold", type: "number", fallback: 0.35 },
        { category: qsTr("Accuracy"), label: qsTr("Learn recurring words"), description: qsTr("Keep notable recurring words in a local vocabulary file."), keywords: "learning dictionary", path: "learning.enabled", type: "switch", fallback: true },
        { category: qsTr("Accuracy"), label: qsTr("Occurrences before learning"), description: qsTr("How many local appearances are required before a word becomes a hint."), keywords: "threshold vocabulary", path: "learning.min_occurrences", type: "number", fallback: 3 },

        { category: qsTr("Text Cleanup"), label: qsTr("Clean up dictated text"), description: qsTr("Remove filler, normalize spacing, and apply spoken layout commands locally."), keywords: "formatting filler", path: "formatting.enabled", type: "switch", fallback: true },
        { category: qsTr("Text Cleanup"), advanced: true, label: qsTr("Use local Ollama when available"), description: qsTr("Apply optional local model polish. Basic cleanup remains available when Ollama is off or unavailable."), keywords: "llm polish", path: "formatting.use_ollama", type: "switch", fallback: true },
        { category: qsTr("Text Cleanup"), advanced: true, label: qsTr("Start local Ollama automatically"), description: qsTr("Start the user's local Ollama process when cleanup needs it."), keywords: "serve model", path: "formatting.autostart_ollama", type: "switch", fallback: true },
        { category: qsTr("Text Cleanup"), advanced: true, label: qsTr("Local Ollama model"), description: qsTr("Exact local model name used for optional cleanup."), keywords: "llama", path: "formatting.ollama_model", type: "text", fallback: "llama3.1:8b" },

        { category: qsTr("Per-App Behavior"), label: qsTr("Manage per-app behavior"), description: qsTr("Open the local configuration file to add, remove, or change exact application behavior values."), keywords: "per-app manage config application", path: "__per_app_config", type: "action", actionText: qsTr("Open local config"), actionKind: "config" },

        { category: qsTr("Privacy"), label: qsTr("Keep microphone ready"), description: qsTr("Keep the local microphone stream open for lower latency. Turning Dictation off always closes it."), keywords: "stream mic indicator", path: "keep_mic_stream_open", type: "switch", fallback: true },
        { category: qsTr("Privacy"), label: qsTr("Rolling RAM audio"), description: qsTr("Seconds held only in RAM and continuously replaced so the first word is not clipped."), keywords: "preroll memory audio", path: "preroll_seconds", type: "number", fallback: 0.4 },
        { category: qsTr("Privacy"), label: qsTr("Screen context"), description: qsTr("Read focused text locally once per dictation to improve spelling. It is held only for that dictation."), keywords: "window spelling local", path: "screen_context.enabled", type: "switch", fallback: true },
        { category: qsTr("Privacy"), label: qsTr("Recent in-memory cleanup context"), description: qsTr("Keep a few recent dictations in memory for local cleanup continuity; never write them as history."), keywords: "recent transcript", path: "formatting.include_recent_context", type: "switch", fallback: true },
        { category: qsTr("Privacy"), label: qsTr("Transcript logging"), description: qsTr("Write dictated text to the local Speakr log. Off is the privacy-preserving default."), keywords: "file history log", path: "log_transcripts", type: "switch", fallback: false },
        { category: qsTr("Privacy"), label: qsTr("Restore clipboard"), description: qsTr("Restore clipboard contents after paste-based insertion."), keywords: "paste", path: "restore_clipboard", type: "switch", fallback: true },

        { category: qsTr("Accessibility"), label: qsTr("Theme"), description: qsTr("Follow the operating system or choose a fixed interface theme."), keywords: "light dark contrast", path: "ui.theme", type: "combo", options: [qsTr("System"), qsTr("Light"), qsTr("Dark"), qsTr("High contrast")], values: ["system", "light", "dark", "high_contrast"], fallback: "system" },
        { category: qsTr("Accessibility"), label: qsTr("Visual effects"), description: qsTr("System follows accessibility and graphics conditions. Full uses native material when available; Reduced limits transparency; Off uses solid surfaces."), keywords: "appearance material mica vibrancy glass transparency effects rendering", path: "ui.visual_effects", type: "combo", options: [qsTr("System"), qsTr("Full"), qsTr("Reduced"), qsTr("Off")], values: ["system", "full", "reduced", "off"], fallback: "system" },
        { category: qsTr("Accessibility"), label: qsTr("Effective appearance"), description: "", keywords: "active effective material mica vibrancy scene glass solid effect tier renderer", path: "__effective_appearance", type: "readonly", fallback: "" },
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
        { category: qsTr("Advanced"), label: qsTr("Raw configuration"), description: qsTr("Open the local configuration file for exact values not shown here."), keywords: "json expert", path: "__raw_config", type: "action", actionText: qsTr("Open local config"), actionKind: "config" }
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

    function perAppRows() {
        var result = []
        var tones = setting("app_tones", ({})) || ({})
        var toneApps = []
        for (var appName in tones) {
            if (tones.hasOwnProperty === undefined || tones.hasOwnProperty(appName))
                toneApps.push(String(appName))
        }
        toneApps.sort()
        if (toneApps.length === 0) {
            result.push({
                category: qsTr("Per-App Behavior"), advanced: true,
                label: qsTr("Per-app tones"),
                description: qsTr("No per-app tones are configured."),
                keywords: "per-app tone configured values none",
                path: "__app_tones_empty", type: "readonly", fallback: ""
            })
        } else {
            for (var toneIndex = 0; toneIndex < toneApps.length; ++toneIndex) {
                var toneApp = toneApps[toneIndex]
                var tone = String(tones[toneApp])
                result.push({
                    category: qsTr("Per-App Behavior"), advanced: true,
                    label: qsTr("Tone for %1").arg(toneApp),
                    description: qsTr("%1 uses the configured %2 tone. This exact value stays in your local configuration file.").arg(toneApp).arg(tone),
                    keywords: "per-app tone configured exact application " + toneApp + " " + tone,
                    path: "__app_tone_" + toneIndex, type: "readonly", fallback: ""
                })
            }
        }

        var exclusions = setting("hotkey_exclude_apps", []) || []
        var excludedApps = []
        if (exclusions.length !== undefined) {
            for (var exclusionIndex = 0; exclusionIndex < exclusions.length; ++exclusionIndex)
                excludedApps.push(String(exclusions[exclusionIndex]))
        }
        excludedApps.sort()
        if (excludedApps.length === 0) {
            result.push({
                category: qsTr("Per-App Behavior"), advanced: true,
                label: qsTr("Shortcut exclusions"),
                description: qsTr("No applications are excluded from the Speakr shortcut."),
                keywords: "excluded-app shortcut exclusions configured values none",
                path: "__excluded_apps_empty", type: "readonly", fallback: ""
            })
        } else {
            for (var excludedIndex = 0; excludedIndex < excludedApps.length; ++excludedIndex) {
                var excludedApp = excludedApps[excludedIndex]
                result.push({
                    category: qsTr("Per-App Behavior"), advanced: true,
                    label: qsTr("Shortcut exclusion for %1").arg(excludedApp),
                    description: qsTr("The Speakr shortcut is disabled while %1 is active. This exact value stays in your local configuration file.").arg(excludedApp),
                    keywords: "excluded-app shortcut exclusion configured exact application " + excludedApp,
                    path: "__excluded_app_" + excludedIndex, type: "readonly", fallback: ""
                })
            }
        }
        return result
    }

    function matches(row) {
        var categoryMatch = selectedCategory === qsTr("All")
                            || row.category === selectedCategory
                            || (selectedCategory === qsTr("Advanced")
                                && Boolean(row.advanced))
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

    function requestedEffectLabel() {
        var value = String(setting("ui.visual_effects", "system"))
        if (value === "full") return qsTr("Full")
        if (value === "reduced") return qsTr("Reduced")
        if (value === "off") return qsTr("Off")
        return qsTr("System")
    }

    function effectTierLabel() {
        var value = root.tokens.effectTier
        try {
            if (nativeWindow !== null && nativeWindow !== undefined)
                value = nativeWindow.effectTier
        } catch (error) {
            // Standalone QML tests intentionally run without native chrome.
        }
        value = String(value)
        if (value === "full") return qsTr("Full effects")
        if (value === "reduced") return qsTr("Reduced effects")
        return qsTr("Effects off")
    }

    function materialLabel() {
        var value = "solid"
        try {
            if (nativeWindow !== null && nativeWindow !== undefined)
                value = nativeWindow.material
        } catch (error) {
            // Standalone QML tests intentionally run without native chrome.
        }
        value = String(value)
        if (value === "mica") return qsTr("Windows Mica")
        if (value === "vibrancy") return qsTr("macOS Vibrancy")
        if (value === "scene_glass") return qsTr("Local scene glass")
        return qsTr("Solid surfaces")
    }

    function effectiveAppearanceSummary() {
        return qsTr("%1 with %2. Accessibility and graphics safeguards can reduce effects without changing your saved choice.")
                .arg(effectTierLabel()).arg(materialLabel())
    }

    function resultsSummary() {
        var category = selectedCategory === qsTr("All")
                     ? qsTr("all categories") : selectedCategory
        var query = searchField.text.trim()
        if (query.length === 0)
            return qsTr("%1 settings in %2").arg(resultCount()).arg(category)
        return qsTr("%1 matches for %2 in %3").arg(resultCount()).arg(query).arg(category)
    }

    function genericSaveError() {
        return qsTr("That setting could not be saved. The previous value is still active.")
    }

    function busySettingExplanation() {
        var issue = appState !== null && appState !== undefined
                  ? appState.last_issue : null
        if (issue !== null && issue !== undefined
                && String(issue.code || "") === "busy_setting") {
            var message = String(issue.message || "").trim()
            if (message.length > 0) return message
        }
        return ""
    }

    function rejectedSettingExplanation() {
        var busyExplanation = busySettingExplanation()
        return busyExplanation.length > 0 ? busyExplanation : genericSaveError()
    }

    function refreshRejectedSettingExplanation(generation) {
        if (generation === rejectedChangeGeneration && lastChange === null)
            saveError = rejectedSettingExplanation()
    }

    function dismissOwnedBusyIssue() {
        var busyExplanation = busySettingExplanation()
        if (busyExplanation.length > 0 && saveError === busyExplanation)
            bridge.dismissIssue()
    }

    function commitChange(path, value, previousValue) {
        dismissOwnedBusyIssue()
        if (!Boolean(bridge.setSetting(path, value))) {
            rejectedChangeGeneration += 1
            var generation = rejectedChangeGeneration
            saveError = genericSaveError()
            lastChange = null
            Qt.callLater(function() {
                root.refreshRejectedSettingExplanation(generation)
            })
            return false
        }
        rejectedChangeGeneration += 1
        lastChange = { path: path, previous: previousValue }
        saveError = ""
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

    Connections {
        target: root.Window.window

        function onActiveFocusItemChanged() {
            if (target !== null && target !== undefined)
                root.queueFocusedItemVisibility(target.activeFocusItem)
        }
    }

    Connections {
        target: scroll.contentItem

        function onContentHeightChanged() {
            var window = root.Window.window
            if (window !== null && window !== undefined
                    && root.isPageDescendant(window.activeFocusItem))
                root.queueFocusedItemVisibility(window.activeFocusItem)
        }

        function onHeightChanged() {
            var window = root.Window.window
            if (window !== null && window !== undefined
                    && root.isPageDescendant(window.activeFocusItem))
                root.queueFocusedItemVisibility(window.activeFocusItem)
        }
    }

    ScrollView {
        id: scroll
        objectName: "settingsScroll"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        Column {
            width: scroll.contentWidth
            spacing: root.tokens.space16

            Item {
                width: parent.width
                height: root.tokens.space8
            }

            GlassSurface {
                objectName: "settingsSearchSurface"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                role: "major"
                padding: root.tokens.space24
                tokens: root.tokens
                implicitHeight: settingsHeader.implicitHeight + padding * 2

                Column {
                    id: settingsHeader
                    anchors.fill: parent
                    spacing: root.tokens.space12

                    PlainText {
                        id: pageHeading
                        width: parent.width
                        text: qsTr("Settings")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.pageHeading
                        font.weight: Font.DemiBold
                        wrapMode: Text.Wrap
                        Accessible.role: Accessible.Heading
                        Accessible.name: text
                    }

                    PlainText {
                        width: parent.width
                        text: qsTr("Tune dictation, privacy, accessibility, and local processing without leaving this device.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }

                    QuietTextField {
                        id: searchField
                        objectName: "settingsSearchField"
                        width: parent.width
                        tokens: root.tokens
                        placeholderText: qsTr("Search settings")
                        accessibleName: qsTr("Search settings")
                        accessibleDescription: qsTr("Search setting labels and descriptions within the selected category")
                    }

                    PlainText {
                        id: resultSummary
                        objectName: "settingsResultSummary"
                        width: parent.width
                        text: root.resultsSummary()
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.secondary
                        wrapMode: Text.Wrap
                        Accessible.role: Accessible.StaticText
                        Accessible.name: text
                    }
                }
            }

            GlassSurface {
                objectName: "settingsCategorySurface"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                role: "navigation"
                padding: root.tokens.space12
                elevated: false
                tokens: root.tokens
                implicitHeight: categoryGrid.implicitHeight + padding * 2

                GridLayout {
                    id: categoryGrid
                    width: parent.width
                    columns: width >= root.tokens.metric(480) ? 3
                             : (width >= root.tokens.metric(300) ? 2 : 1)
                    columnSpacing: root.tokens.space8
                    rowSpacing: root.tokens.space8
                    Accessible.role: Accessible.PageTabList
                    Accessible.name: qsTr("Settings categories")

                    Repeater {
                        model: root.categories

                        delegate: NavigationButton {
                            required property string modelData
                            Layout.fillWidth: true
                            tokens: root.tokens
                            text: modelData
                            selected: root.selectedCategory === modelData
                            onClicked: root.selectedCategory = modelData
                        }
                    }
                }
            }

            InlineNotice {
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                visible: root.lastChange !== null
                tokens: root.tokens
                kind: "success"
                title: qsTr("Saved on this device")
                message: qsTr("Your most recent setting is active.")
                actionText: qsTr("Undo")
                actionDescription: qsTr("Restore the previous value for the most recent setting")
                onActionRequested: {
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

            GlassSurface {
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                visible: root.pendingSensitiveChange !== null
                role: "notice"
                padding: root.tokens.space16
                fillColor: root.tokens.warningSurface
                edgeColor: root.tokens.warning
                tokens: root.tokens
                implicitHeight: transcriptWarning.implicitHeight + padding * 2
                Accessible.role: Accessible.AlertMessage
                Accessible.name: qsTr("Confirm transcript logging")

                Column {
                    id: transcriptWarning
                    anchors.fill: parent
                    spacing: root.tokens.space8

                    SectionHeading {
                        width: parent.width
                        tokens: root.tokens
                        title: qsTr("Confirm transcript logging")
                        description: qsTr("This creates a persistent local transcript record. Practice text is never logged.")
                    }

                    PlainText {
                        width: parent.width
                        text: qsTr("Dictated text will be written to %1 on this device. Turn this on only if you want that local record.")
                              .arg(String(root.setting("log_path", "speakr.log")))
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }

                    Flow {
                        width: parent.width
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

            InlineNotice {
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                visible: root.saveError.length > 0
                tokens: root.tokens
                kind: "danger"
                title: qsTr("Setting not saved")
                message: root.saveError
            }

            GlassSurface {
                objectName: "settingsRowsSurface"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                role: "content"
                padding: root.tokens.space16
                elevated: false
                tokens: root.tokens
                implicitHeight: settingRows.implicitHeight + padding * 2

                Column {
                    id: settingRows
                    anchors.fill: parent
                    spacing: 0

                    Column {
                        id: settingsRowsList
                        objectName: "settingsRowsRepeater"
                        width: parent.width
                        spacing: 0

                        Repeater {
                            model: root.rows

                            delegate: SettingRow {
                                required property var modelData
                                readonly property string resolvedDescription: modelData.path === "__effective_appearance"
                                                                             ? root.effectiveAppearanceSummary()
                                                                             : (modelData.path === "toggle_mode"
                                                                                && Boolean(root.setting("toggle_mode_forced", false))
                                                                                ? qsTr("Windows key combinations always use Press to start and stop. Change to a single-key shortcut to choose Hold to speak.")
                                                                                : modelData.description)
                                objectName: "settingRow_" + modelData.path
                                width: settingsRowsList.width
                                visible: root.matches(modelData)
                                height: visible ? implicitHeight : 0
                                tokens: root.tokens
                                label: modelData.label
                                description: resolvedDescription
                                category: modelData.category
                                path: modelData.path
                                controlType: modelData.type
                                options: modelData.options || []
                                values: modelData.values || []
                                currentValue: modelData.path === "toggle_mode"
                                              ? root.setting("effective_toggle_mode",
                                                             root.setting("toggle_mode", modelData.fallback))
                                              : (modelData.type === "hotkey"
                                              ? (root.appState.hotkey || root.setting(modelData.path, modelData.fallback))
                                              : root.setting(modelData.path, modelData.fallback))
                                controlEnabled: !(modelData.path === "toggle_mode"
                                                  && Boolean(root.setting("toggle_mode_forced", false)))
                                showCategory: root.selectedCategory === qsTr("All")
                                              || searchField.text.trim().length > 0
                                              || (root.selectedCategory === qsTr("Advanced")
                                                  && modelData.category !== qsTr("Advanced"))
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
                    }

                    GlassSurface {
                        width: parent.width
                        visible: (root.selectedCategory === qsTr("Accessibility")
                                  || root.selectedCategory === qsTr("Advanced"))
                                 && searchField.text.trim().length === 0
                        role: "notice"
                        padding: root.tokens.space16
                        elevated: false
                        tokens: root.tokens
                        implicitHeight: renderingDetails.implicitHeight + padding * 2

                        Column {
                            id: renderingDetails
                            anchors.fill: parent
                            spacing: root.tokens.space8

                            StatusOrb {
                                objectName: "effectiveAppearanceStatus"
                                width: parent.width
                                tokens: root.tokens
                                statusKind: root.effectTierLabel() === qsTr("Effects off") ? "neutral" : "active"
                                label: qsTr("%1 · %2").arg(root.effectTierLabel()).arg(root.materialLabel())
                                description: qsTr("The effective visual appearance for this window")
                            }

                            PlainText {
                                id: effectiveAppearanceText
                                objectName: "effectiveAppearanceText"
                                width: parent.width
                                text: qsTr("Saved choice: %1. High Contrast, Reduce Transparency, remote desktop, or software rendering can automatically reduce effects.")
                                      .arg(root.requestedEffectLabel())
                                color: root.tokens.mutedText
                                font.family: root.tokens.fontFamily
                                font.pixelSize: root.tokens.secondary
                                wrapMode: Text.Wrap
                            }
                        }
                    }

                    Column {
                        id: noResults
                        objectName: "settingsEmptyState"
                        width: parent.width
                        visible: root.resultCount() === 0
                        spacing: root.tokens.space12
                        Accessible.role: Accessible.Note
                        Accessible.name: qsTr("No settings match")

                        StatusOrb {
                            x: Math.round((parent.width - width) / 2)
                            tokens: root.tokens
                            statusKind: "neutral"
                            symbol: "?"
                            label: qsTr("No settings match")
                        }

                        PlainText {
                            width: parent.width
                            text: qsTr("Try a broader term, clear the search, or choose All categories.")
                            color: root.tokens.mutedText
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.body
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                        }

                        QuietButton {
                            x: Math.round((parent.width - width) / 2)
                            tokens: root.tokens
                            text: qsTr("Clear search")
                            kind: "primary"
                            accessibleDescription: qsTr("Clear the search and show all setting categories")
                            onClicked: {
                                searchField.clear()
                                root.selectedCategory = qsTr("All")
                                searchField.forceActiveFocus(Qt.TabFocusReason)
                            }
                        }
                    }
                }
            }

            Item {
                width: parent.width
                height: root.tokens.space24
            }
        }
    }
}
