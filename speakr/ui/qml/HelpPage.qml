import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: root
    objectName: "helpPage"

    required property var tokens
    property var appState: ({})
    property var settings: ({})
    property string pendingResetSection: ""
    property string resetError: ""
    property int rejectedResetGeneration: 0
    property int focusScrollGeneration: 0
    signal repeatSetupRequested()

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

    function value(source, key, fallbackValue) {
        if (source !== null && source !== undefined
                && source[key] !== null && source[key] !== undefined)
            return source[key]
        return fallbackValue
    }

    function resetInterface() {
        return Boolean(bridge.resetSettingsSection("interface"))
    }

    function resetPrivacy() {
        return Boolean(bridge.resetSettingsSection("privacy"))
    }

    function materialSummary() {
        var material = "solid"
        try {
            if (nativeWindow !== null && nativeWindow !== undefined)
                material = nativeWindow.material
        } catch (error) {
            // Standalone QML tests intentionally run without native chrome.
        }
        material = String(material)
        if (material === "mica") return qsTr("Windows Mica")
        if (material === "vibrancy") return qsTr("macOS Vibrancy")
        if (material === "scene_glass") return qsTr("Local scene glass")
        return qsTr("Solid surfaces")
    }

    function effectSummary() {
        var tier = root.tokens.effectTier
        try {
            if (nativeWindow !== null && nativeWindow !== undefined)
                tier = nativeWindow.effectTier
        } catch (error) {
            // Standalone QML tests intentionally run without native chrome.
        }
        tier = String(tier)
        if (tier === "full") return qsTr("Full")
        if (tier === "reduced") return qsTr("Reduced")
        return qsTr("Off")
    }

    function requestReset(section) {
        rejectedResetGeneration += 1
        pendingResetSection = section
        resetError = ""
        Qt.callLater(function() {
            resetCancel.forceActiveFocus(Qt.TabFocusReason)
            root.queueFocusedItemVisibility(resetCancel)
        })
    }

    function genericResetError() {
        return qsTr("Those defaults could not be restored. Your current settings are unchanged.")
    }

    function resetIssueExplanation() {
        var issue = appState !== null && appState !== undefined
                  ? appState.last_issue : null
        if (issue !== null && issue !== undefined) {
            var code = String(issue.code || "")
            var message = String(issue.message || "").trim()
            if (code === "busy_setting"
                    && message.length > 0)
                return message
        }
        return ""
    }

    function rejectedResetExplanation() {
        var issueExplanation = resetIssueExplanation()
        return issueExplanation.length > 0 ? issueExplanation : genericResetError()
    }

    function refreshRejectedResetExplanation(generation) {
        if (generation === rejectedResetGeneration
                && pendingResetSection.length > 0)
            resetError = rejectedResetExplanation()
    }

    function dismissOwnedBusyIssue() {
        var busyExplanation = resetIssueExplanation()
        if (busyExplanation.length > 0 && resetError === busyExplanation)
            bridge.dismissIssue()
    }

    function cancelReset() {
        rejectedResetGeneration += 1
        pendingResetSection = ""
        resetError = ""
    }

    function confirmReset() {
        var section = pendingResetSection
        if (section.length === 0) return false
        dismissOwnedBusyIssue()
        var succeeded = section === "interface" ? resetInterface()
                      : (section === "privacy" ? resetPrivacy() : false)
        if (succeeded) {
            rejectedResetGeneration += 1
            pendingResetSection = ""
            resetError = ""
            return true
        }
        rejectedResetGeneration += 1
        var generation = rejectedResetGeneration
        resetError = genericResetError()
        Qt.callLater(function() {
            root.refreshRejectedResetExplanation(generation)
        })
        return false
    }

    function microphoneSummary() {
        var activeValue = root.value(root.settings, "active_input_device", "")
        var configuredValue = root.value(root.settings, "input_device", "")
        var active = activeValue === null || activeValue === undefined ? "" : String(activeValue)
        var configured = configuredValue === null || configuredValue === undefined
                         ? "" : String(configuredValue)
        var activeLabel = active.length > 0 ? active : qsTr("System default")
        var configuredLabel = configured.length > 0 ? configured : qsTr("System default")
        return active === configured
                ? activeLabel
                : qsTr("%1; restart to use %2").arg(activeLabel).arg(configuredLabel)
    }

    function sampleRateSummary() {
        var active = Number(root.value(root.settings, "active_sample_rate", 16000))
        var configured = Number(root.value(root.settings, "sample_rate", active))
        return active === configured
                ? qsTr("%1 Hz").arg(active)
                : qsTr("%1 Hz; restart to use %2 Hz").arg(active).arg(configured)
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
        objectName: "helpScroll"
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
                objectName: "helpHeroSurface"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                role: "major"
                padding: root.tokens.space24
                tokens: root.tokens
                implicitHeight: helpHeader.implicitHeight + padding * 2

                Column {
                    id: helpHeader
                    anchors.fill: parent
                    spacing: root.tokens.space12

                    PlainText {
                        id: pageHeading
                        width: parent.width
                        text: qsTr("Help & diagnostics")
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
                        text: qsTr("Repair local setup, inspect exact device details, or reopen the guided setup.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }

                    StatusOrb {
                        width: parent.width
                        tokens: root.tokens
                        statusKind: "success"
                        label: qsTr("Everything stays on this device")
                        description: qsTr("Speakr has no telemetry, cloud account, or remote transcription")
                    }
                }
            }

            InlineNotice {
                objectName: "helpPrivacyNotice"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                tokens: root.tokens
                kind: "success"
                title: qsTr("Private by design")
                message: qsTr("Audio, transcripts, screen context, learned vocabulary, diagnostics, and usage data do not leave this computer.")
                detail: qsTr("The only non-loopback activity is a one-time speech-model download. Optional Ollama cleanup uses 127.0.0.1; basic cleanup works without it.")
            }

            GlassSurface {
                objectName: "repairSetupSurface"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                role: "content"
                padding: root.tokens.space16
                elevated: false
                tokens: root.tokens
                implicitHeight: repairContent.implicitHeight + padding * 2

                Column {
                    id: repairContent
                    anchors.fill: parent
                    spacing: root.tokens.space12

                    SectionHeading {
                        width: parent.width
                        tokens: root.tokens
                        title: qsTr("Repair setup")
                        description: qsTr("If Speakr cannot hear you or insert text, review microphone, Accessibility, Input Monitoring, or automation permissions.")
                    }

                    Flow {
                        width: parent.width
                        spacing: root.tokens.space8

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Open system settings")
                            kind: "primary"
                            accessibleDescription: qsTr("Open local operating system privacy and permission settings")
                            onClicked: bridge.openSystemSettings()
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Recheck local setup")
                            accessibleDescription: qsTr("Dismiss the current issue and retry microphone and model initialization")
                            onClicked: bridge.retrySetup()
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Repeat guided setup")
                            kind: "quiet"
                            accessibleDescription: qsTr("Open the first-run setup again without deleting vocabulary")
                            onClicked: root.repeatSetupRequested()
                        }
                    }
                }
            }

            GlassSurface {
                objectName: "localSetupSurface"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                role: "content"
                padding: root.tokens.space16
                elevated: false
                tokens: root.tokens
                implicitHeight: diagnosticContent.implicitHeight + padding * 2

                Column {
                    id: diagnosticContent
                    anchors.fill: parent
                    spacing: 0

                    SectionHeading {
                        width: parent.width
                        tokens: root.tokens
                        title: qsTr("Current local setup")
                        description: qsTr("These values describe the active session, not a remote report.")
                    }

                    Repeater {
                        model: [
                            { label: qsTr("Status"), value: String(root.value(root.appState, "primary", root.value(root.appState, "availability", "starting"))) },
                            { label: qsTr("Microphone"), value: root.microphoneSummary() },
                            { label: qsTr("Sample rate"), value: root.sampleRateSummary() },
                            { label: qsTr("Speech model"), value: String(root.value(root.appState, "model", "Automatic")) },
                            { label: qsTr("Processing device"), value: String(root.value(root.appState, "device", "unknown")).toUpperCase() },
                            { label: qsTr("Compute type"), value: String(root.value(root.appState, "compute_type", root.value(root.settings, "compute_type_in_use", "unknown"))).toUpperCase() },
                            { label: qsTr("Text cleanup"), value: root.value(root.appState, "cleanup_path", "rules") === "ollama" ? qsTr("Local Ollama available") : qsTr("Basic cleanup active") },
                            { label: qsTr("Visual effects"), value: qsTr("%1 · %2").arg(root.effectSummary()).arg(root.materialSummary()) },
                            { label: qsTr("Queue"), value: qsTr("%1 local jobs").arg(root.value(root.appState, "queue_depth", 0)) }
                        ]

                        delegate: Item {
                            required property var modelData
                            width: parent.width
                            implicitHeight: diagnosticRow.implicitHeight + root.tokens.space24

                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                height: root.tokens.borderWidth
                                color: root.tokens.border
                                Accessible.ignored: true
                            }

                            GridLayout {
                                id: diagnosticRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                columns: width >= root.tokens.metric(500) ? 2 : 1
                                columnSpacing: root.tokens.space24
                                rowSpacing: root.tokens.space4
                                Accessible.role: Accessible.StaticText
                                Accessible.name: qsTr("%1: %2").arg(modelData.label).arg(modelData.value)

                                PlainText {
                                    Layout.fillWidth: true
                                    text: modelData.label
                                    color: root.tokens.text
                                    font.family: root.tokens.fontFamily
                                    font.pixelSize: root.tokens.body
                                    font.weight: Font.Medium
                                    wrapMode: Text.Wrap
                                    Accessible.ignored: true
                                }

                                PlainText {
                                    Layout.fillWidth: true
                                    text: modelData.value
                                    color: root.tokens.mutedText
                                    font.family: root.tokens.fontFamily
                                    font.pixelSize: root.tokens.body
                                    wrapMode: Text.Wrap
                                    Accessible.ignored: true
                                }
                            }
                        }
                    }
                }
            }

            GlassSurface {
                objectName: "localFilesSurface"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                role: "notice"
                padding: root.tokens.space16
                elevated: false
                tokens: root.tokens
                implicitHeight: filesContent.implicitHeight + padding * 2

                Column {
                    id: filesContent
                    anchors.fill: parent
                    spacing: root.tokens.space12

                    SectionHeading {
                        width: parent.width
                        tokens: root.tokens
                        title: qsTr("Local files and recovery")
                        description: qsTr("Open diagnostics or the loopback-only recovery panel. No file is uploaded.")
                    }

                    Flow {
                        width: parent.width
                        spacing: root.tokens.space8

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Open log")
                            accessibleDescription: qsTr("Open the local diagnostic log")
                            onClicked: bridge.openLocal("log")
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Open config")
                            accessibleDescription: qsTr("Open the local configuration file")
                            onClicked: bridge.openLocal("config")
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Open dictionary")
                            accessibleDescription: qsTr("Open the local dictionary file")
                            onClicked: bridge.openLocal("dictionary")
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Open local browser fallback")
                            accessibleDescription: qsTr("Open Speakr's loopback-only browser control panel")
                            onClicked: bridge.openBrowserFallback()
                        }
                    }
                }
            }

            GlassSurface {
                objectName: "resetSettingsSurface"
                x: root.tokens.space32
                width: Math.max(0, parent.width - root.tokens.space32 * 2)
                role: "notice"
                padding: root.tokens.space16
                elevated: false
                tokens: root.tokens
                implicitHeight: resetContent.implicitHeight + padding * 2

                Column {
                    id: resetContent
                    anchors.fill: parent
                    spacing: root.tokens.space12

                    SectionHeading {
                        width: parent.width
                        tokens: root.tokens
                        title: qsTr("Restore defaults by section")
                        description: qsTr("These actions keep your vocabulary and speech-model files. You will confirm before anything changes.")
                    }

                    Flow {
                        width: parent.width
                        visible: root.pendingResetSection.length === 0
                        spacing: root.tokens.space8

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Reset interface")
                            kind: "danger"
                            accessibleDescription: qsTr("Review restoring interface, HUD, text size, and motion defaults")
                            onClicked: root.requestReset("interface")
                        }

                        QuietButton {
                            tokens: root.tokens
                            text: qsTr("Reset privacy")
                            kind: "danger"
                            accessibleDescription: qsTr("Review restoring privacy controls to their recommended local defaults")
                            onClicked: root.requestReset("privacy")
                        }
                    }

                    InlineNotice {
                        objectName: "resetConfirmation"
                        width: parent.width
                        visible: root.pendingResetSection.length > 0
                        tokens: root.tokens
                        kind: "warning"
                        title: root.pendingResetSection === "interface"
                               ? qsTr("Reset interface settings?")
                               : qsTr("Reset privacy settings?")
                        message: qsTr("The selected section returns to its recommended local defaults. Vocabulary and speech models remain unchanged.")
                        detail: root.resetError
                    }

                    Flow {
                        width: parent.width
                        visible: root.pendingResetSection.length > 0
                        spacing: root.tokens.space8

                        QuietButton {
                            id: resetCancel
                            objectName: "resetCancelButton"
                            tokens: root.tokens
                            text: qsTr("Cancel")
                            kind: "primary"
                            accessibleDescription: qsTr("Keep current settings")
                            onClicked: root.cancelReset()
                        }

                        QuietButton {
                            objectName: "resetConfirmButton"
                            tokens: root.tokens
                            text: qsTr("Restore defaults")
                            kind: "danger"
                            accessibleDescription: qsTr("Confirm restoring the selected section")
                            onClicked: root.confirmReset()
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
