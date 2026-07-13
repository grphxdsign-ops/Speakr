import QtQuick
import QtQuick.Layouts

Item {
    id: root

    required property var tokens
    property int activeStage: 0 // 0 idle, 1 transcribe, 2 clean up, 3 insert, 4 complete
    property bool compact: false
    property bool accessibilityEnabled: true

    implicitWidth: tokens.metric(360)
    implicitHeight: compact ? tokens.metric(38) : tokens.metric(52)
    Accessible.role: Accessible.List
    Accessible.name: qsTr("Processing stages")
    Accessible.ignored: !accessibilityEnabled

    RowLayout {
        anchors.fill: parent
        spacing: root.tokens.space8

        SignalNode {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: root.tokens.metric(root.compact ? 72 : 100)
            tokens: root.tokens
            accessibilityEnabled: root.accessibilityEnabled
            label: root.compact ? qsTr("Transcribe") : qsTr("Transcribe")
            active: root.activeStage === 1
            reached: root.activeStage > 1
        }

        Rectangle {
            objectName: "signalConnector"
            readonly property color edgeColor: root.tokens.text
            Layout.fillWidth: true
            Layout.minimumWidth: root.tokens.metric(8)
            Layout.preferredWidth: root.tokens.metric(root.compact ? 24 : 40)
            Layout.alignment: Qt.AlignVCenter
            implicitWidth: root.tokens.metric(32)
            implicitHeight: root.tokens.metric(root.tokens.highContrast ? 6 : 3)
            Layout.preferredHeight: implicitHeight
            radius: height / 2
            color: root.tokens.highContrast ? root.tokens.surface
                                            : root.tokens.border
            border.width: root.tokens.highContrast ? root.tokens.borderWidth : 0
            border.color: edgeColor

            Rectangle {
                objectName: "signalConnectorFill"
                anchors.fill: parent
                anchors.margins: root.tokens.highContrast
                                 ? root.tokens.borderWidth : 0
                radius: height / 2
                color: root.tokens.accentForeground
                transform: Scale {
                    origin.x: 0
                    origin.y: 0
                    xScale: root.activeStage > 1 ? 1 : 0
                    Behavior on xScale {
                        NumberAnimation {
                            duration: root.tokens.motionStage
                            easing.type: Easing.OutQuint
                        }
                    }
                }
            }
        }

        SignalNode {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: root.tokens.metric(root.compact ? 72 : 100)
            tokens: root.tokens
            accessibilityEnabled: root.accessibilityEnabled
            label: qsTr("Clean up")
            active: root.activeStage === 2
            reached: root.activeStage > 2
        }

        Rectangle {
            objectName: "signalConnector"
            readonly property color edgeColor: root.tokens.text
            Layout.fillWidth: true
            Layout.minimumWidth: root.tokens.metric(8)
            Layout.preferredWidth: root.tokens.metric(root.compact ? 24 : 40)
            Layout.alignment: Qt.AlignVCenter
            implicitWidth: root.tokens.metric(32)
            implicitHeight: root.tokens.metric(root.tokens.highContrast ? 6 : 3)
            Layout.preferredHeight: implicitHeight
            radius: height / 2
            color: root.tokens.highContrast ? root.tokens.surface
                                            : root.tokens.border
            border.width: root.tokens.highContrast ? root.tokens.borderWidth : 0
            border.color: edgeColor

            Rectangle {
                objectName: "signalConnectorFill"
                anchors.fill: parent
                anchors.margins: root.tokens.highContrast
                                 ? root.tokens.borderWidth : 0
                radius: height / 2
                color: root.tokens.accentForeground
                transform: Scale {
                    origin.x: 0
                    origin.y: 0
                    xScale: root.activeStage > 2 ? 1 : 0
                    Behavior on xScale {
                        NumberAnimation {
                            duration: root.tokens.motionStage
                            easing.type: Easing.OutQuint
                        }
                    }
                }
            }
        }

        SignalNode {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: root.tokens.metric(root.compact ? 72 : 100)
            tokens: root.tokens
            accessibilityEnabled: root.accessibilityEnabled
            label: qsTr("Insert")
            active: root.activeStage === 3
            reached: root.activeStage > 3
        }
    }
}
