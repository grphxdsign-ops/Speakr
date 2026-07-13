import QtQuick
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: root
    objectName: "hudWindow"

    property var appState: bridge.state || ({})
    property var settingsMap: bridge.settings || ({})
    property bool focusGuardSuppressed: false
    readonly property string visibilityPreference: String(setting("ui.hud_visibility", "while_dictating"))
    readonly property bool large: String(setting("ui.hud_size", "standard")) === "large"
    readonly property real hudScale: Math.max(
                                         1.0,
                                         Math.min(2.0,
                                                  Math.max(numericSetting("ui.hud_scale", 100),
                                                           numericSetting("ui.text_scale", 100)) / 100.0))
    readonly property bool pipelineHasJob: Number(value(appState, "pipeline_job_id",
                                                        value(appState, "job_id", 0))) > 0
    readonly property bool outcomeHasJob:
        (Number(value(appState, "pipeline_job_id", 0)) > 0
         || Number(value(appState, "capture_job_id", 0)) > 0)
        && (["no_speech", "mic_recovery", "edit_failure"]
             .indexOf(String(value(appState, "status_code", ""))) >= 0
            || (["microphone_unavailable", "microphone_reconnected"]
                 .indexOf(String(value(value(appState, "last_issue", ({})),
                                       "code", ""))) >= 0))
    readonly property bool hudActive: value(appState, "capture", "idle") === "listening"
                                      || (value(appState, "pipeline", "idle") !== "idle"
                                          && pipelineHasJob)
                                      || outcomeHasJob
    readonly property bool shouldShow: visibilityPreference !== "off"
                                       && !bridge.quitting
                                       && !focusGuardSuppressed
                                       && (visibilityPreference === "always" || hudActive)
    readonly property bool reducedMotion: tokens.reduceMotion

    width: Math.min(Math.round((large ? 460 : 360) * hudScale),
                    Math.max(240, monitorWidth() - Math.round(32 * hudScale)))
    height: Math.round((large ? 128 : 96) * hudScale)
    x: clamp(monitorX() + (monitorWidth() - width) / 2,
             monitorX() + Math.round(8 * hudScale),
             monitorX() + monitorWidth() - width - Math.round(8 * hudScale))
    y: String(setting("ui.hud_edge", "bottom")) === "top"
       ? clamp(monitorY() + Math.round(24 * hudScale),
               monitorY(), monitorY() + monitorHeight() - height)
       : clamp(monitorY() + monitorHeight() - height - Math.round(24 * hudScale),
               monitorY(), monitorY() + monitorHeight() - height)
    visible: shouldShow
    color: "transparent"
    flags: Qt.FramelessWindowHint
           | Qt.Tool
           | Qt.WindowStaysOnTopHint
           | Qt.WindowTransparentForInput
           | Qt.WindowDoesNotAcceptFocus
    modality: Qt.NonModal
    title: qsTr("Speakr status")

    function value(source, key, fallbackValue) {
        if (source !== null && source !== undefined
                && source[key] !== null && source[key] !== undefined)
            return source[key]
        return fallbackValue
    }

    function setting(path, fallbackValue) {
        var source = settingsMap || ({})
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

    function numericSetting(path, fallbackValue) {
        var result = Number(setting(path, fallbackValue))
        return isFinite(result) ? result : Number(fallbackValue)
    }

    function motionPreference() {
        var result = setting("ui.reduced_motion", setting("ui.motion", "system"))
        if (result === true || String(result) === "reduce") return "reduced"
        return String(result)
    }

    function fallbackGeometry(name, fallbackValue) {
        if (name === "x") return Number(Screen.virtualX)
        if (name === "y") return Number(Screen.virtualY)
        if (name === "width") {
            var availableWidth = Number(Screen.desktopAvailableWidth)
            return availableWidth > 0 ? availableWidth : Number(Screen.width)
        }
        if (name === "height") {
            var availableHeight = Number(Screen.desktopAvailableHeight)
            return availableHeight > 0 ? availableHeight : Number(Screen.height)
        }
        return fallbackValue
    }

    function monitorX() {
        var suppliedWidth = Number(value(appState, "active_monitor_width", 0))
        return suppliedWidth > 0
                ? Number(value(appState, "active_monitor_x", 0))
                : fallbackGeometry("x", 0)
    }

    function monitorY() {
        var suppliedHeight = Number(value(appState, "active_monitor_height", 0))
        return suppliedHeight > 0
                ? Number(value(appState, "active_monitor_y", 0))
                : fallbackGeometry("y", 0)
    }

    function monitorWidth() {
        var supplied = Number(value(appState, "active_monitor_width", 0))
        return supplied > 0 ? supplied : Math.max(1, fallbackGeometry("width", Screen.width))
    }

    function monitorHeight() {
        var supplied = Number(value(appState, "active_monitor_height", 0))
        return supplied > 0 ? supplied : Math.max(1, fallbackGeometry("height", Screen.height))
    }

    function clamp(numberValue, minimumValue, maximumValue) {
        if (maximumValue < minimumValue) return minimumValue
        return Math.max(minimumValue, Math.min(maximumValue, numberValue))
    }

    function pipelineText(pipeline) {
        if (pipeline === "queued") return qsTr("Waiting for an earlier dictation")
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
        return ""
    }

    function primaryText() {
        if (value(appState, "availability", "ready") === "needs_attention")
            return value(appState, "primary", qsTr("Speakr needs attention"))
        if (value(appState, "capture", "idle") === "listening")
            return value(appState, "capture_mode", value(appState, "mode", "dictation")) === "edit"
                    ? qsTr("Listening for an edit instruction") : qsTr("Listening")
        var pipeline = String(value(appState, "pipeline", "idle"))
        if (pipeline !== "idle") return pipelineText(pipeline)
        if (root.outcomeHasJob)
            return value(appState, "primary", qsTr("Nothing was inserted"))
        if (!Boolean(value(appState, "enabled", true))) return qsTr("Dictation is off")
        if (value(appState, "availability", "ready") === "starting") return qsTr("Getting Speakr ready")
        return qsTr("Ready")
    }

    function secondaryText() {
        var custom = String(value(appState, "secondary", ""))
        if (custom.length > 0) return custom
        var pipeline = String(value(appState, "pipeline", "idle"))
        if (value(appState, "capture", "idle") === "listening" && pipeline !== "idle")
            return qsTr("Previous dictation: %1").arg(pipelineText(pipeline))
        if (Number(value(appState, "queue_depth", 0)) > 0)
            return qsTr("%1 local dictations waiting").arg(value(appState, "queue_depth", 0))
        if (pipeline === "error")
            return value(appState, "detail", qsTr("Nothing was changed. Try again when ready."))
        if (value(appState, "capture", "idle") === "listening")
            return qsTr("Release your shortcut when you are finished")
        if (pipeline !== "idle") return qsTr("Everything stays on this device")
        return qsTr("Everything stays on this device")
    }

    function stage() {
        var pipeline = String(value(appState, "pipeline", "idle"))
        if (pipeline === "queued" || pipeline === "waiting_model" || pipeline === "transcribing") return 1
        if (pipeline === "formatting") return 2
        if (pipeline === "injecting") return 3
        if (pipeline === "success") return 4
        return 0
    }

    function micSegments() {
        var band = String(value(appState, "mic_level_band", "silent"))
        if (band === "high") return 5
        if (band === "good") return 4
        if (band === "low") return 2
        return 0
    }

    function isError() {
        return value(appState, "availability", "ready") === "needs_attention"
                || value(appState, "pipeline", "idle") === "error"
    }

    Theme {
        id: tokens
        mode: String(root.setting("ui.theme", "system"))
        density: "compact"
        textScale: root.hudScale
        reduceMotion: root.motionPreference() === "reduced"
                      || (root.motionPreference() === "system"
                          && Boolean(root.setting("system_reduced_motion", false)))
        systemHighContrast: Boolean(root.setting("system_high_contrast", false))
    }

    onVisibleChanged: {
        if (visible) entrance.restart()
    }

    Rectangle {
        id: panel
        anchors.fill: parent
        opacity: 1
        radius: tokens.radiusLarge
        color: root.isError() ? tokens.dangerSurface : tokens.surface
        border.width: tokens.highContrast ? 2 : 1
        border.color: root.isError() ? tokens.danger : tokens.border
        Behavior on color {
            ColorAnimation { duration: tokens.motionStandard }
        }
        Behavior on border.color {
            ColorAnimation { duration: tokens.motionStandard }
        }
        Accessible.role: Accessible.AlertMessage
        Accessible.name: root.primaryText()
        Accessible.description: root.secondaryText()
        Accessible.ignored: !Boolean(root.setting("ui.background_announcements", false))
        transform: [
            Scale {
                id: panelScale
                origin.x: panel.width / 2
                origin.y: panel.height / 2
                xScale: 1
                yScale: 1
            },
            Translate { id: panelShift; y: 0 }
        ]

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: root.large ? tokens.space12 : tokens.space8
            spacing: tokens.space4

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: tokens.metric(root.large ? 48 : 36)
                spacing: tokens.space12

                Item {
                    Layout.preferredWidth: tokens.metric(36)
                    Layout.fillHeight: true
                    Accessible.ignored: true

                    Rectangle {
                        anchors.centerIn: parent
                        visible: root.value(root.appState, "capture", "idle") !== "listening"
                        width: tokens.metric(30)
                        height: width
                        radius: width / 2
                        color: root.isError()
                               ? tokens.danger
                               : (root.value(root.appState, "pipeline", "idle") === "success"
                                  ? tokens.success : tokens.accent)

                        PlainText {
                            readonly property bool success:
                                root.value(root.appState, "pipeline", "idle") === "success"
                            anchors.centerIn: parent
                            text: root.isError() ? "!"
                                                 : (success ? "✓" : "•")
                            color: tokens.highContrast && root.isError()
                                   ? tokens.background : tokens.accentText
                            font.family: tokens.fontFamily
                            font.pixelSize: tokens.statusHeading
                            font.weight: Font.Bold
                            scale: success ? 1 : 0.86
                            Behavior on scale {
                                NumberAnimation {
                                    duration: tokens.reduceMotion ? 0 : 180
                                    easing.type: Easing.OutQuint
                                }
                            }
                        }
                    }

                    Row {
                        anchors.centerIn: parent
                        visible: root.value(root.appState, "capture", "idle") === "listening"
                        spacing: tokens.space4

                        Repeater {
                            model: 5
                            Rectangle {
                                required property int index
                                width: tokens.metric(4)
                                height: tokens.metric(10 + index % 3 * 4)
                                anchors.verticalCenter: parent.verticalCenter
                                radius: width / 2
                                color: index < root.micSegments() ? tokens.accent : tokens.border

                                Behavior on color {
                                    ColorAnimation { duration: tokens.motionFast }
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    PlainText {
                        Layout.fillWidth: true
                        Layout.preferredHeight: tokens.metric(root.large ? 24 : 18)
                        text: root.primaryText()
                        color: tokens.text
                        font.family: tokens.fontFamily
                        font.pixelSize: tokens.statusHeading
                        font.weight: Font.DemiBold
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }

                    PlainText {
                        Layout.fillWidth: true
                        Layout.preferredHeight: tokens.metric(root.large ? 22 : 18)
                        text: root.secondaryText()
                        color: tokens.mutedText
                        font.family: tokens.fontFamily
                        font.pixelSize: tokens.secondary
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }
            }

            SignalPath {
                Layout.fillWidth: true
                Layout.fillHeight: true
                tokens: tokens
                compact: true
                activeStage: root.stage()
            }
        }
    }

    ParallelAnimation {
        id: entrance
        NumberAnimation {
            target: panel
            property: "opacity"
            from: root.reducedMotion ? 1 : 0
            to: 1
            duration: root.reducedMotion ? 0 : 160
            easing.type: Easing.OutQuint
        }
        NumberAnimation {
            target: panelScale
            properties: "xScale,yScale"
            from: root.reducedMotion ? 1 : 0.98
            to: 1
            duration: root.reducedMotion ? 0 : 160
            easing.type: Easing.OutQuint
        }
        NumberAnimation {
            target: panelShift
            property: "y"
            from: root.reducedMotion ? 0 : tokens.metric(8)
            to: 0
            duration: root.reducedMotion ? 0 : 160
            easing.type: Easing.OutQuint
        }
    }
}
