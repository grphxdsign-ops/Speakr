import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    required property var tokens
    property var appState: ({})
    property var settings: ({})
    signal repeatSetupRequested()

    function focusHeading() {
        pageHeading.forceActiveFocus(Qt.OtherFocusReason)
    }

    function value(source, key, fallbackValue) {
        if (source !== null && source !== undefined
                && source[key] !== null && source[key] !== undefined)
            return source[key]
        return fallbackValue
    }

    function resetInterface() {
        bridge.resetSettingsSection("interface")
    }

    function resetPrivacy() {
        bridge.resetSettingsSection("privacy")
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
                spacing: root.tokens.space8

                Text {
                    id: pageHeading
                    Layout.fillWidth: true
                    text: qsTr("Help & diagnostics")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.pageHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                    Accessible.name: text
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Repair local setup, inspect device details, or reopen the guided setup.")
                    color: root.tokens.mutedText
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    wrapMode: Text.Wrap
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                implicitHeight: privacyContent.implicitHeight + root.tokens.space32
                radius: root.tokens.radiusLarge
                color: root.tokens.successSurface
                border.width: 1
                border.color: root.tokens.success

                ColumnLayout {
                    id: privacyContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: root.tokens.space16
                    spacing: root.tokens.space8

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Everything stays on this device")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.sectionHeading
                        font.weight: Font.DemiBold
                        wrapMode: Text.Wrap
                        Accessible.role: Accessible.Heading
                    }

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Speakr does not send audio, transcripts, screen context, learned vocabulary, diagnostics, or usage data away from this computer. The only non-loopback network activity is a one-time local speech-model download.")
                        color: root.tokens.text
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.body
                        wrapMode: Text.Wrap
                    }

                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Optional Ollama cleanup uses only 127.0.0.1 on your own machine. Basic cleanup works without Ollama.")
                        color: root.tokens.mutedText
                        font.family: root.tokens.fontFamily
                        font.pixelSize: root.tokens.secondary
                        wrapMode: Text.Wrap
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: root.tokens.space12

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Repair setup")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.sectionHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("If Speakr cannot hear you or insert text, review microphone, Accessibility, Input Monitoring, or automation permissions in system settings.")
                    color: root.tokens.mutedText
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.body
                    wrapMode: Text.Wrap
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: root.tokens.space12

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
                        accessibleDescription: qsTr("Open the first-run setup again without deleting vocabulary")
                        onClicked: root.repeatSetupRequested()
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
                    text: qsTr("Current local setup")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.sectionHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
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
                        { label: qsTr("Queue"), value: qsTr("%1 local jobs").arg(root.value(root.appState, "queue_depth", 0)) }
                    ]

                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: diagnosticRow.implicitHeight + root.tokens.space24
                        color: "transparent"

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            height: 1
                            color: root.tokens.border
                        }

                        GridLayout {
                            id: diagnosticRow
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

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: root.tokens.space12

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Local files and fallback")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.sectionHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                }

                Flow {
                    Layout.fillWidth: true
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

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: root.tokens.space32
                Layout.rightMargin: root.tokens.space32
                spacing: root.tokens.space12

                Text {
                    text: qsTr("Restore defaults by section")
                    color: root.tokens.text
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.sectionHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("These actions keep your vocabulary and speech model files.")
                    color: root.tokens.mutedText
                    font.family: root.tokens.fontFamily
                    font.pixelSize: root.tokens.secondary
                    wrapMode: Text.Wrap
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: root.tokens.space8

                    QuietButton {
                        tokens: root.tokens
                        text: qsTr("Reset interface")
                        kind: "danger"
                        accessibleDescription: qsTr("Restore interface, HUD, text size, and motion defaults")
                        onClicked: root.resetInterface()
                    }

                    QuietButton {
                        tokens: root.tokens
                        text: qsTr("Reset privacy")
                        kind: "danger"
                        accessibleDescription: qsTr("Restore privacy controls to their recommended local defaults")
                        onClicked: root.resetPrivacy()
                    }
                }
            }

            Item { Layout.preferredHeight: root.tokens.space24 }
        }
    }
}
