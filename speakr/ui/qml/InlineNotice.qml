import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    required property var tokens
    property string kind: "info" // info | success | warning | danger
    property string title: ""
    property string message: ""
    property string detail: ""
    property string actionText: ""
    property string actionDescription: ""
    readonly property color semanticColor: kind === "success" ? tokens.success
                                            : (kind === "warning" ? tokens.warning
                                               : (kind === "danger" ? tokens.danger
                                                                   : tokens.info))
    readonly property color semanticSurface: kind === "success" ? tokens.successSurface
                                              : (kind === "warning" ? tokens.warningSurface
                                                 : (kind === "danger" ? tokens.dangerSurface
                                                                     : tokens.infoSurface))

    signal actionRequested()

    implicitHeight: Math.max(tokens.controlHeight,
                             noticeLayout.implicitHeight + tokens.space24)
    radius: tokens.radiusControl
    color: tokens.highContrast ? tokens.surface : semanticSurface
    border.width: tokens.borderWidth
    border.color: semanticColor
    Accessible.role: kind === "danger" || kind === "warning"
                     ? Accessible.AlertMessage : Accessible.StaticText
    Accessible.name: title.length > 0 ? title : message
    Accessible.description: detail.length > 0 ? message + ". " + detail : message

    GridLayout {
        id: noticeLayout
        objectName: "noticeLayout"
        anchors.fill: parent
        anchors.margins: root.tokens.space12
        columns: 2
        columnSpacing: root.tokens.space12
        rowSpacing: root.tokens.space8

        Rectangle {
            objectName: "noticeIcon"
            readonly property color edgeColor: root.tokens.highContrast
                                                  ? root.tokens.accentText
                                                  : root.semanticColor
            Layout.preferredWidth: root.tokens.metric(28)
            Layout.preferredHeight: Layout.preferredWidth
            Layout.minimumWidth: Layout.preferredWidth
            Layout.maximumWidth: Layout.preferredWidth
            Layout.alignment: Qt.AlignTop
            radius: width / 2
            color: root.tokens.highContrast
                   ? root.tokens.accent
                   : root.tokens.withAlpha(root.semanticColor, 0.16)
            border.width: 1
            border.color: edgeColor

            PlainText {
                objectName: "noticeIconGlyph"
                anchors.centerIn: parent
                text: root.kind === "success" ? "\u2713"
                      : (root.kind === "danger" ? "\u00d7"
                         : (root.kind === "warning" ? "!" : "i"))
                color: root.tokens.highContrast ? root.tokens.accentText
                                                : root.semanticColor
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.body
                font.weight: Font.Bold
                Accessible.ignored: true
            }
        }

        ColumnLayout {
            objectName: "noticeTextColumn"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: root.tokens.space4

            PlainText {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                visible: root.title.length > 0
                text: root.title
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.body
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
                Accessible.ignored: true
            }

            PlainText {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: root.message
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.secondary
                wrapMode: Text.Wrap
                Accessible.ignored: true
            }

            PlainText {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                visible: root.detail.length > 0
                text: root.detail
                color: root.tokens.mutedText
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.secondary
                wrapMode: Text.Wrap
                Accessible.ignored: true
            }
        }

        QuietButton {
            id: noticeActionButton
            objectName: "noticeAction"
            visible: root.actionText.length > 0
            Layout.columnSpan: 2
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: noticeLayout.width
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            tokens: root.tokens
            text: root.actionText
            kind: "secondary"
            implicitHeight: Math.max(root.tokens.controlHeight,
                                     noticeActionLabel.implicitHeight
                                     + root.tokens.space16)
            accessibleDescription: root.actionDescription
            onClicked: root.actionRequested()

            contentItem: PlainText {
                id: noticeActionLabel
                objectName: "noticeActionLabel"
                text: noticeActionButton.text
                color: noticeActionButton.resolvedContentColor
                font.family: noticeActionButton.tokens.fontFamily
                font.pixelSize: noticeActionButton.tokens.label
                font.weight: Font.Medium
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.Wrap
                elide: Text.ElideNone
                Accessible.ignored: true
            }
        }
    }
}
