pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: root
    objectName: "hudWindow"

    // Context properties are supplied by the native Qt bootstrap.
    // qmllint disable unqualified
    property var appState: bridge.state || ({})
    property var settingsMap: bridge.settings || ({})
    property var nativeController: typeof nativeWindow === "undefined" ? null : nativeWindow
    property bool focusGuardSuppressed: false

    readonly property string visibilityPreference: String(setting("ui.hud_visibility", "while_dictating"))
    readonly property bool large: String(setting("ui.hud_size", "standard")) === "large"
    readonly property real hudScale: Math.max(1.0, Math.min(2.0, Math.max(numericSetting("ui.hud_scale", 100), numericSetting("ui.text_scale", 100)) / 100.0))
    readonly property bool pipelineHasJob: Number(value(appState, "pipeline_job_id", value(appState, "job_id", 0))) > 0
    readonly property bool outcomeHasJob: (Number(value(appState, "pipeline_job_id", 0)) > 0 || Number(value(appState, "capture_job_id", 0)) > 0) && (["no_speech", "mic_recovery", "edit_failure"].indexOf(String(value(appState, "status_code", ""))) >= 0 || (["microphone_unavailable", "microphone_reconnected"].indexOf(String(value(value(appState, "last_issue", ({})), "code", ""))) >= 0))
    readonly property bool hudActive: value(appState, "capture", "idle") === "listening" || (value(appState, "pipeline", "idle") !== "idle" && pipelineHasJob) || outcomeHasJob
    readonly property bool shouldShow: visibilityPreference !== "off" && !bridge.quitting && !focusGuardSuppressed && (visibilityPreference === "always" || hudActive)
    // qmllint enable unqualified
    readonly property bool reducedMotion: tokens.reduceMotion

    readonly property string desiredPrimary: primaryText()
    readonly property string desiredSecondary: secondaryText()
    readonly property string desiredKind: stateKind()
    property string animatedPrimary: desiredPrimary
    property string animatedSecondary: desiredSecondary
    property string animatedKind: desiredKind
    readonly property string displayedPrimary: reducedMotion ? desiredPrimary : animatedPrimary
    readonly property string displayedSecondary: reducedMotion ? desiredSecondary : animatedSecondary
    readonly property string displayedKind: reducedMotion ? desiredKind : animatedKind

    width: Math.min(Math.round((large ? 460 : 360) * hudScale), Math.max(240, monitorWidth() - Math.round(32 * hudScale)))
    height: Math.round((large ? 128 : 96) * hudScale)
    x: clamp(monitorX() + (monitorWidth() - width) / 2, monitorX() + Math.round(8 * hudScale), monitorX() + monitorWidth() - width - Math.round(8 * hudScale))
    y: String(setting("ui.hud_edge", "bottom")) === "top" ? clamp(monitorY() + Math.round(24 * hudScale), monitorY(), monitorY() + monitorHeight() - height) : clamp(monitorY() + monitorHeight() - height - Math.round(24 * hudScale), monitorY(), monitorY() + monitorHeight() - height)
    visible: shouldShow
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
    modality: Qt.NonModal
    title: qsTr("Speakr status")

    function value(source, key, fallbackValue) {
        if (source !== null && source !== undefined && source[key] !== null && source[key] !== undefined)
            return source[key];
        return fallbackValue;
    }

    function setting(path, fallbackValue) {
        var source = settingsMap || ({});
        if (source[path] !== undefined && source[path] !== null)
            return source[path];
        var parts = path.split(".");
        for (var i = 0; i < parts.length; ++i) {
            if (source === null || source === undefined || source[parts[i]] === undefined)
                return fallbackValue;
            source = source[parts[i]];
        }
        return source === undefined ? fallbackValue : source;
    }

    function numericSetting(path, fallbackValue) {
        var result = Number(setting(path, fallbackValue));
        return isFinite(result) ? result : Number(fallbackValue);
    }

    function motionPreference() {
        var result = setting("ui.reduced_motion", setting("ui.motion", "system"));
        if (result === true || String(result) === "reduce")
            return "reduced";
        return String(result);
    }

    function fallbackGeometry(name, fallbackValue) {
        if (name === "x")
            return Number(Screen.virtualX);
        if (name === "y")
            return Number(Screen.virtualY);
        if (name === "width") {
            var availableWidth = Number(Screen.desktopAvailableWidth);
            return availableWidth > 0 ? availableWidth : Number(Screen.width);
        }
        if (name === "height") {
            var availableHeight = Number(Screen.desktopAvailableHeight);
            return availableHeight > 0 ? availableHeight : Number(Screen.height);
        }
        return fallbackValue;
    }

    function monitorX() {
        var suppliedWidth = Number(value(appState, "active_monitor_width", 0));
        return suppliedWidth > 0 ? Number(value(appState, "active_monitor_x", 0)) : fallbackGeometry("x", 0);
    }

    function monitorY() {
        var suppliedHeight = Number(value(appState, "active_monitor_height", 0));
        return suppliedHeight > 0 ? Number(value(appState, "active_monitor_y", 0)) : fallbackGeometry("y", 0);
    }

    function monitorWidth() {
        var supplied = Number(value(appState, "active_monitor_width", 0));
        return supplied > 0 ? supplied : Math.max(1, fallbackGeometry("width", Screen.width));
    }

    function monitorHeight() {
        var supplied = Number(value(appState, "active_monitor_height", 0));
        return supplied > 0 ? supplied : Math.max(1, fallbackGeometry("height", Screen.height));
    }

    function clamp(numberValue, minimumValue, maximumValue) {
        if (maximumValue < minimumValue)
            return minimumValue;
        return Math.max(minimumValue, Math.min(maximumValue, numberValue));
    }

    function pipelineText(pipeline) {
        if (pipeline === "queued")
            return qsTr("Waiting for an earlier dictation");
        if (pipeline === "waiting_model")
            return qsTr("Waiting for the speech model");
        if (pipeline === "transcribing")
            return qsTr("Transcribing locally");
        if (pipeline === "formatting")
            return value(appState, "pipeline_mode", value(appState, "mode", "dictation")) === "edit" ? qsTr("Applying your instruction locally") : qsTr("Cleaning up locally");
        if (pipeline === "injecting")
            return qsTr("Inserting text");
        if (pipeline === "success")
            return value(appState, "pipeline_mode", value(appState, "mode", "dictation")) === "edit" ? qsTr("Selection updated") : qsTr("Inserted");
        if (pipeline === "error")
            return value(appState, "primary", qsTr("Nothing was inserted"));
        return "";
    }

    function primaryText() {
        if (value(appState, "availability", "ready") === "needs_attention")
            return value(appState, "primary", qsTr("Speakr needs attention"));
        if (value(appState, "capture", "idle") === "listening")
            return value(appState, "capture_mode", value(appState, "mode", "dictation")) === "edit" ? qsTr("Listening for an edit instruction") : qsTr("Listening");
        var pipeline = String(value(appState, "pipeline", "idle"));
        if (pipeline !== "idle")
            return pipelineText(pipeline);
        if (root.outcomeHasJob)
            return value(appState, "primary", qsTr("Nothing was inserted"));
        if (!Boolean(value(appState, "enabled", true)))
            return qsTr("Dictation is off");
        if (value(appState, "availability", "ready") === "starting")
            return qsTr("Getting Speakr ready");
        return qsTr("Ready");
    }

    function secondaryText() {
        var pipeline = String(value(appState, "pipeline", "idle"));
        if (value(appState, "capture", "idle") === "listening" && pipeline !== "idle")
            return qsTr("Previous dictation: %1").arg(pipelineText(pipeline));
        var custom = String(value(appState, "secondary", ""));
        if (custom.length > 0)
            return custom;
        if (Number(value(appState, "queue_depth", 0)) > 0)
            return qsTr("%1 local dictations waiting").arg(value(appState, "queue_depth", 0));
        if (pipeline === "error")
            return value(appState, "detail", qsTr("Nothing was changed. Try again when ready."));
        if (value(appState, "capture", "idle") === "listening")
            return qsTr("Release your shortcut when you are finished");
        return qsTr("Everything stays on this device");
    }

    function stage() {
        var pipeline = String(value(appState, "pipeline", "idle"));
        if (pipeline === "queued" || pipeline === "waiting_model" || pipeline === "transcribing")
            return 1;
        if (pipeline === "formatting")
            return 2;
        if (pipeline === "injecting")
            return 3;
        if (pipeline === "success")
            return 4;
        return 0;
    }

    function micSegments() {
        var band = String(value(appState, "mic_level_band", "silent"));
        if (band === "high")
            return 5;
        if (band === "good")
            return 4;
        if (band === "low")
            return 2;
        return 0;
    }

    function isError() {
        return value(appState, "availability", "ready") === "needs_attention" || (value(appState, "capture", "idle") !== "listening" && value(appState, "pipeline", "idle") === "error");
    }

    function stateKind() {
        if (isError())
            return "danger";
        if (value(appState, "capture", "idle") === "listening")
            return "listening";
        if (["no_speech", "mic_recovery", "edit_failure"].indexOf(String(value(appState, "status_code", ""))) >= 0)
            return "warning";
        if (value(appState, "pipeline", "idle") === "success")
            return "success";
        if (value(appState, "pipeline", "idle") !== "idle")
            return "active";
        return "neutral";
    }

    function stateColor(kind) {
        if (kind === "danger")
            return tokens.danger;
        if (kind === "warning")
            return tokens.warning;
        if (kind === "success")
            return tokens.success;
        if (kind === "active" || kind === "listening")
            return tokens.accent;
        return tokens.border;
    }

    function syncDisplayedState() {
        var enteringSuccess = desiredKind === "success" && animatedKind !== "success";
        animatedPrimary = desiredPrimary;
        animatedSecondary = desiredSecondary;
        animatedKind = desiredKind;
        if (enteringSuccess && !reducedMotion)
            Qt.callLater(root.startSuccessBloom);
    }

    function startSuccessBloom() {
        if (displayedKind === "success")
            successBloom.restart();
    }

    function transitionDisplayedState() {
        if (reducedMotion) {
            stateCrossfade.stop();
            stateContent.opacity = 1;
            syncDisplayedState();
            return;
        }
        stateCrossfade.restart();
    }

    Theme {
        id: tokens
        objectName: "hudTheme"
        mode: String(root.setting("ui.theme", "system"))
        density: "compact"
        textScale: root.hudScale
        reduceMotion: root.motionPreference() === "reduced" || (root.motionPreference() === "system" && Boolean(root.setting("system_reduced_motion", false)))
        systemHighContrast: Boolean(root.setting("system_high_contrast", false))
        visualEffects: String(root.setting("ui.visual_effects", "system"))
        systemReduceTransparency: root.nativeController !== null ? Boolean(root.nativeController.systemReduceTransparency) : Boolean(root.setting("ui.system_reduce_transparency", root.setting("system_reduce_transparency", false)))
        softwareRenderer: root.nativeController !== null ? Boolean(root.nativeController.softwareRenderer) : Boolean(root.setting("ui.software_renderer", root.setting("software_renderer", false)))
    }

    onDesiredPrimaryChanged: transitionDisplayedState()
    onDesiredSecondaryChanged: transitionDisplayedState()
    onDesiredKindChanged: transitionDisplayedState()
    onReducedMotionChanged: {
        if (reducedMotion)
            syncDisplayedState();
    }
    onVisibleChanged: {
        if (visible)
            entrance.restart();
    }

    GlassSurface {
        id: panel
        objectName: "hudPanel"
        anchors.fill: parent
        tokens: tokens
        role: "hud"
        cornerRadius: tokens.radiusPanel
        padding: 0
        elevated: false
        fillColor: root.displayedKind === "danger" ? tokens.dangerSurface : tokens.hudSurface
        edgeColor: root.stateColor(root.displayedKind)
        Accessible.role: Accessible.AlertMessage
        Accessible.name: root.displayedPrimary
        Accessible.description: root.displayedSecondary
        Accessible.ignored: !Boolean(root.setting("ui.background_announcements", false))
        transform: [
            Scale {
                id: panelScale
                origin.x: panel.width / 2
                origin.y: panel.height / 2
                xScale: 1
                yScale: 1
            },
            Translate {
                id: panelShift
                y: 0
            }
        ]

        Behavior on fillColor {
            ColorAnimation {
                duration: tokens.motionStandard
            }
        }
        Behavior on edgeColor {
            ColorAnimation {
                duration: tokens.motionStandard
            }
        }

        Item {
            objectName: "hudAtmosphere"
            anchors.fill: parent
            clip: true
            visible: !tokens.highContrast && tokens.effectTier === "full"
            Accessible.ignored: true

            Rectangle {
                width: tokens.metric(140)
                height: width
                radius: width / 2
                x: -width * 0.56
                y: -height * 0.48
                color: "transparent"
                border.width: tokens.borderWidth
                border.color: tokens.atmosphereViolet
            }

            Rectangle {
                width: tokens.metric(104)
                height: width
                radius: width / 2
                x: parent.width - width * 0.44
                y: parent.height - height * 0.42
                color: "transparent"
                border.width: tokens.borderWidth
                border.color: tokens.atmosphereCyan
            }
        }

        Item {
            id: stateContent
            objectName: "hudStateContent"
            anchors.fill: parent
            anchors.leftMargin: root.large ? tokens.space12 : tokens.space8
            anchors.rightMargin: anchors.leftMargin
            anchors.topMargin: root.large ? tokens.space12 : Math.round(tokens.space4 / 2)
            anchors.bottomMargin: anchors.topMargin
            opacity: 1

            ColumnLayout {
                anchors.fill: parent
                spacing: root.large ? tokens.space4 : 0

                RowLayout {
                    id: statusRow
                    Layout.fillWidth: true
                    Layout.minimumHeight: statusCopy.implicitHeight
                    Layout.preferredHeight: Math.max(tokens.metric(root.large ? 48 : 36), statusCopy.implicitHeight)
                    Layout.maximumHeight: root.large ? Math.max(tokens.metric(48), statusCopy.implicitHeight) : statusCopy.implicitHeight
                    spacing: tokens.space12

                    Item {
                        objectName: "hudStateIcon"
                        Layout.preferredWidth: tokens.metric(root.large ? 40 : 36)
                        Layout.fillHeight: true
                        Accessible.ignored: true

                        Rectangle {
                            id: successRing
                            objectName: "hudSuccessRing"
                            anchors.centerIn: parent
                            visible: root.displayedKind === "success"
                            width: tokens.metric(34)
                            height: width
                            radius: width / 2
                            color: "transparent"
                            border.width: tokens.borderWidth
                            border.color: tokens.success
                            opacity: 0
                            scale: 1
                        }

                        Rectangle {
                            objectName: "hudStateBadge"
                            anchors.centerIn: parent
                            visible: root.displayedKind !== "listening"
                            width: tokens.metric(30)
                            height: width
                            radius: width / 2
                            color: tokens.highContrast ? root.stateColor(root.displayedKind) : tokens.withAlpha(root.stateColor(root.displayedKind), 0.18)
                            border.width: tokens.highContrast ? 2 : 1
                            border.color: root.stateColor(root.displayedKind)

                            PlainText {
                                id: stateGlyph
                                objectName: "hudStateGlyph"
                                anchors.centerIn: parent
                                text: root.displayedKind === "danger" ? "!" : (root.displayedKind === "warning" ? "!" : (root.displayedKind === "success" ? "\u2713" : "\u2022"))
                                color: tokens.highContrast ? ((root.displayedKind === "active" || root.displayedKind === "success") ? tokens.accentText : tokens.background) : root.stateColor(root.displayedKind)
                                font.family: tokens.fontFamily
                                font.pixelSize: tokens.statusHeading
                                font.weight: Font.Bold
                                Accessible.ignored: true
                            }
                        }

                        Row {
                            id: levelMeter
                            objectName: "hudLevelMeter"
                            anchors.centerIn: parent
                            visible: root.displayedKind === "listening"
                            spacing: tokens.space4

                            Repeater {
                                model: 5

                                Rectangle {
                                    required property int index
                                    width: tokens.metric(4)
                                    height: tokens.metric(18)
                                    radius: width / 2
                                    color: index < root.micSegments() ? tokens.accent : tokens.border
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        id: statusCopy
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: 0

                        PlainText {
                            id: primaryLabel
                            objectName: "hudPrimaryText"
                            Layout.fillWidth: true
                            Layout.minimumHeight: implicitHeight
                            Layout.preferredHeight: implicitHeight
                            text: root.displayedPrimary
                            color: tokens.text
                            font.family: tokens.fontFamily
                            font.pixelSize: tokens.statusHeading
                            font.weight: Font.DemiBold
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            Accessible.ignored: true
                        }

                        PlainText {
                            id: secondaryLabel
                            objectName: "hudSecondaryText"
                            Layout.fillWidth: true
                            Layout.minimumHeight: implicitHeight
                            Layout.preferredHeight: implicitHeight
                            text: root.displayedSecondary
                            color: tokens.mutedText
                            font.family: tokens.fontFamily
                            font.pixelSize: tokens.secondary
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            Accessible.ignored: true
                        }
                    }
                }

                SignalPath {
                    objectName: "hudSignalPath"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: implicitHeight
                    tokens: tokens
                    compact: true
                    activeStage: root.stage()
                }
            }
        }
    }

    SequentialAnimation {
        id: stateCrossfade

        NumberAnimation {
            target: stateContent
            property: "opacity"
            from: 1
            to: 0
            duration: Math.round(tokens.motionStandard / 2)
            easing.type: Easing.InQuad
        }
        ScriptAction {
            script: root.syncDisplayedState()
        }
        NumberAnimation {
            target: stateContent
            property: "opacity"
            from: 0
            to: 1
            duration: Math.round(tokens.motionStandard / 2)
            easing.type: Easing.OutQuad
        }
    }

    ParallelAnimation {
        id: successBloom
        objectName: "hudSuccessBloom"

        NumberAnimation {
            target: successRing
            property: "scale"
            from: 0.78
            to: 1.18
            duration: tokens.motionEmphasis
            easing.type: Easing.OutQuint
        }
        SequentialAnimation {
            NumberAnimation {
                target: successRing
                property: "opacity"
                from: 0
                to: 0.42
                duration: Math.round(tokens.motionEmphasis * 0.35)
            }
            NumberAnimation {
                target: successRing
                property: "opacity"
                from: 0.42
                to: 0
                duration: Math.round(tokens.motionEmphasis * 0.65)
            }
        }
        NumberAnimation {
            target: stateGlyph
            property: "scale"
            from: tokens.reduceMotion ? 1 : 0.82
            to: 1
            duration: tokens.motionEmphasis
            easing.type: Easing.OutQuint
        }
    }

    ParallelAnimation {
        id: entrance

        NumberAnimation {
            target: panel
            property: "opacity"
            from: root.reducedMotion ? 1 : 0
            to: 1
            duration: tokens.motionStandard
            easing.type: Easing.OutQuint
        }
        NumberAnimation {
            target: panelScale
            properties: "xScale,yScale"
            from: root.reducedMotion ? 1 : 0.98
            to: 1
            duration: tokens.motionStandard
            easing.type: Easing.OutQuint
        }
        NumberAnimation {
            target: panelShift
            property: "y"
            from: root.reducedMotion ? 0 : tokens.metric(8)
            to: 0
            duration: tokens.motionStandard
            easing.type: Easing.OutQuint
        }
    }
}
