pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Vertical setup step rail per the approved onboarding storyboard: done,
// current, and upcoming nodes with a 220 ms check draw on completion and a
// 160 ms connector fill between steps. State is never color alone: each node
// pairs its dot with a number or drawn check plus a written state line.
ColumnLayout {
    id: rail
    objectName: "onboardingStepRail"

    required property var tokens
    property var stepNames: []
    property int currentStep: 0

    signal stepActivated(int index)

    spacing: 0
    Accessible.role: Accessible.PageTabList
    Accessible.name: qsTr("Setup steps")

    function stepStateText(index) {
        if (index < currentStep) return qsTr("Completed")
        if (index === currentStep) return qsTr("Current")
        return qsTr("Upcoming")
    }

    function stepDescription(index) {
        var number = index + 1
        var total = stepNames.length
        if (index < currentStep)
            return qsTr("Completed setup step %1 of %2. Activate to return.")
                    .arg(number).arg(total)
        if (index === currentStep)
            return qsTr("Current setup step %1 of %2.").arg(number).arg(total)
        return qsTr("Upcoming setup step %1 of %2. Complete the current step first.")
                .arg(number).arg(total)
    }

    Repeater {
        model: rail.stepNames

        delegate: AbstractButton {
            id: stepNode

            required property int index
            required property string modelData
            readonly property bool done: index < rail.currentStep
            readonly property bool current: index === rail.currentStep
            readonly property bool last: index === rail.stepNames.length - 1

            objectName: "onboardingStepButton" + index
            Layout.fillWidth: true
            implicitHeight: Math.max(rail.tokens.controlHeight,
                                     implicitContentHeight
                                     + topPadding + bottomPadding)
            implicitWidth: implicitContentWidth + leftPadding + rightPadding
            padding: rail.tokens.space4
            enabled: index <= rail.currentStep
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            text: qsTr("%1. %2").arg(index + 1).arg(modelData)

            Accessible.role: Accessible.Button
            Accessible.name: text
            Accessible.description: rail.stepDescription(index)

            onClicked: rail.stepActivated(index)

            background: Item {
                Rectangle {
                    anchors.fill: parent
                    radius: rail.tokens.radiusControl
                    color: stepNode.enabled && stepNode.hovered
                           ? rail.tokens.hover : "transparent"

                    Behavior on color {
                        ColorAnimation { duration: rail.tokens.motionHover }
                    }
                }

                FocusRing {
                    anchors.fill: parent
                    tokens: rail.tokens
                    shown: stepNode.visualFocus
                    cornerRadius: rail.tokens.radiusControl
                }
            }

            contentItem: RowLayout {
                spacing: rail.tokens.space12

                ColumnLayout {
                    Layout.fillHeight: true
                    Layout.preferredWidth: rail.tokens.metric(28)
                    Layout.alignment: Qt.AlignTop
                    spacing: rail.tokens.space4

                    Rectangle {
                        id: stepDot
                        objectName: "onboardingStepDot" + stepNode.index
                        Layout.preferredWidth: rail.tokens.metric(28)
                        Layout.preferredHeight: rail.tokens.metric(28)
                        radius: height / 2
                        color: stepNode.current
                               ? rail.tokens.accent
                               : (rail.tokens.highContrast
                                  ? rail.tokens.surface : "transparent")
                        border.width: rail.tokens.borderWidth
                        border.color: stepNode.done || stepNode.current
                                      ? rail.tokens.accentForeground
                                      : rail.tokens.border

                        Behavior on color {
                            ColorAnimation { duration: rail.tokens.motionStandard }
                        }
                        Behavior on border.color {
                            ColorAnimation { duration: rail.tokens.motionStandard }
                        }

                        PlainText {
                            anchors.centerIn: parent
                            visible: !stepNode.done
                            text: String(stepNode.index + 1)
                            color: stepNode.current
                                   ? rail.tokens.accentText
                                   : rail.tokens.mutedText
                            font.family: rail.tokens.fontFamily
                            font.pixelSize: rail.tokens.secondary
                            font.weight: Font.DemiBold
                            Accessible.ignored: true
                        }

                        CheckDraw {
                            objectName: "onboardingStepCheck" + stepNode.index
                            anchors.centerIn: parent
                            width: rail.tokens.metric(14)
                            height: rail.tokens.metric(14)
                            tokens: rail.tokens
                            visible: stepNode.done
                            drawn: stepNode.done
                            strokeColor: rail.tokens.highContrast
                                         ? rail.tokens.text
                                         : rail.tokens.accentForeground
                        }
                    }

                    Item {
                        visible: !stepNode.last
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillHeight: true
                        Layout.preferredWidth: rail.tokens.metric(
                                                   rail.tokens.highContrast ? 4 : 2)
                        Layout.minimumHeight: rail.tokens.space8

                        Rectangle {
                            objectName: "onboardingStepConnector" + stepNode.index
                            anchors.fill: parent
                            radius: width / 2
                            color: rail.tokens.highContrast
                                   ? rail.tokens.surface : rail.tokens.border

                            Rectangle {
                                objectName: "onboardingStepConnectorFill"
                                            + stepNode.index
                                readonly property bool filled: stepNode.done
                                anchors.fill: parent
                                radius: width / 2
                                color: rail.tokens.accentForeground
                                transform: Scale {
                                    origin.y: 0
                                    yScale: stepNode.done ? 1 : 0

                                    Behavior on yScale {
                                        NumberAnimation {
                                            duration: rail.tokens.motionStage
                                            easing.type: Easing.OutQuint
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    spacing: 0

                    PlainText {
                        Layout.fillWidth: true
                        text: stepNode.modelData
                        color: stepNode.current
                               ? rail.tokens.text : rail.tokens.mutedText
                        font.family: rail.tokens.fontFamily
                        font.pixelSize: rail.tokens.body
                        font.weight: stepNode.current
                                     ? Font.DemiBold : Font.Medium
                        wrapMode: Text.Wrap
                        Accessible.ignored: true

                        Behavior on color {
                            ColorAnimation { duration: rail.tokens.motionStandard }
                        }
                    }

                    PlainText {
                        objectName: "onboardingStepState" + stepNode.index
                        Layout.fillWidth: true
                        text: rail.stepStateText(stepNode.index)
                        color: rail.tokens.mutedText
                        font.family: rail.tokens.fontFamily
                        font.pixelSize: rail.tokens.secondary
                        wrapMode: Text.Wrap
                        Accessible.ignored: true
                    }
                }
            }
        }
    }
}
