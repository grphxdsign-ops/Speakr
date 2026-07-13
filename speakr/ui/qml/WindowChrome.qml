pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

Item {
    id: root

    required property var tokens
    property var controller: null
    property var hostWindow: null
    readonly property bool controlsOnLeft: Qt.platform.os === "osx"
    readonly property bool maximized: controller !== null && Boolean(controller.maximized)

    implicitHeight: Math.max(tokens.metric(64), controlRow.implicitHeight + tokens.space16)
    Accessible.role: Accessible.Pane
    Accessible.name: qsTr("Speakr title bar")

    function sceneRect(item) {
        var point = item.mapToItem(null, 0, 0)
        return Qt.rect(point.x, point.y, item.width, item.height)
    }

    function reportHitRegions() {
        if (controller === null || !Boolean(controller.customChromeEnabled))
            return
        controller.setHitRegions(sceneRect(dragRegion),
                                 sceneRect(minimizeButton),
                                 sceneRect(maximizeButton),
                                 sceneRect(closeButton),
                                 tokens.space8)
    }

    function invokeAction(action) {
        if (controller !== null) {
            if (action === "minimize") controller.minimize()
            else if (action === "maximize" || action === "restore") controller.toggleMaximize()
            else if (action === "close") controller.closeMain()
            return
        }
        if (hostWindow === null) return
        if (action === "minimize") hostWindow.showMinimized()
        else if (action === "maximize") hostWindow.showMaximized()
        else if (action === "restore") hostWindow.showNormal()
        else if (action === "close") hostWindow.close()
    }

    Item {
        id: dragRegion
        objectName: "titlebarDragRegion"
        anchors.fill: parent

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            property point pressPoint: Qt.point(0, 0)
            property bool moveStarted: false

            onPressed: function(mouse) {
                pressPoint = Qt.point(mouse.x, mouse.y)
                moveStarted = false
            }
            onPositionChanged: function(mouse) {
                if (!pressed || moveStarted || !(pressedButtons & Qt.LeftButton)) return
                var distance = Math.abs(mouse.x - pressPoint.x) + Math.abs(mouse.y - pressPoint.y)
                if (distance >= root.tokens.space8 && root.controller !== null) {
                    moveStarted = Boolean(root.controller.beginSystemMove())
                }
            }
            onDoubleClicked: function(mouse) {
                if (mouse.button === Qt.LeftButton) root.invokeAction(root.maximized ? "restore" : "maximize")
            }
            onClicked: function(mouse) {
                if (mouse.button !== Qt.RightButton || root.controller === null) return
                var point = dragRegion.mapToItem(null, mouse.x, mouse.y)
                root.controller.showSystemMenu(point.x, point.y)
            }
        }
    }

    RowLayout {
        id: titleContent
        anchors.fill: parent
        anchors.leftMargin: root.controlsOnLeft
                            ? controlRow.width + root.tokens.space24 : root.tokens.space24
        anchors.rightMargin: root.controlsOnLeft
                             ? root.tokens.space24 : controlRow.width + root.tokens.space24
        spacing: root.tokens.space16

        RowLayout {
            spacing: root.tokens.space8
            Accessible.role: Accessible.Graphic
            Accessible.name: qsTr("Speakr signal path")

            RowLayout {
                spacing: root.tokens.space4
                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        Layout.preferredWidth: root.tokens.metric(index === 1 ? 10 : 8)
                        Layout.preferredHeight: Layout.preferredWidth
                        radius: width / 2
                        color: index === 1 ? root.tokens.accent : root.tokens.text
                        Accessible.ignored: true
                    }
                }
            }

            PlainText {
                text: qsTr("Speakr")
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.sectionHeading
                font.weight: Font.DemiBold
                Accessible.ignored: true
            }
        }

        Item { Layout.fillWidth: true }

        RowLayout {
            visible: root.width >= root.tokens.metric(720)
                     && root.tokens.textScale <= 1.5
            spacing: root.tokens.space8
            Accessible.role: Accessible.Note
            Accessible.name: qsTr("Everything stays on this device")

            Rectangle {
                Layout.preferredWidth: root.tokens.metric(10)
                Layout.preferredHeight: Layout.preferredWidth
                radius: width / 2
                color: root.tokens.success
                Accessible.ignored: true
            }
            PlainText {
                text: qsTr("Everything stays on this device")
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.secondary
                font.weight: Font.Medium
                Accessible.ignored: true
            }
        }
    }

    Item {
        id: controlRow
        objectName: "windowControlGroup"
        readonly property real buttonStep: minimizeButton.implicitWidth
                                                + root.tokens.space4
        implicitWidth: minimizeButton.implicitWidth * 3 + root.tokens.space8
        implicitHeight: Math.max(minimizeButton.implicitHeight,
                                 maximizeButton.implicitHeight,
                                 closeButton.implicitHeight)
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: root.controlsOnLeft ? parent.left : undefined
        anchors.right: root.controlsOnLeft ? undefined : parent.right
        anchors.leftMargin: root.tokens.space8
        anchors.rightMargin: root.tokens.space8
        Accessible.role: Accessible.Grouping
        Accessible.name: qsTr("Window controls")

        ChromeButton {
            id: minimizeButton
            objectName: "minimizeWindowButton"
            x: root.controlsOnLeft ? controlRow.buttonStep : 0
            anchors.verticalCenter: parent.verticalCenter
            tokens: root.tokens
            windowAction: "minimize"
            accessibleDescription: qsTr("Minimize Speakr to the taskbar or Dock")
            onActionRequested: function(action) { root.invokeAction(action) }
        }
        ChromeButton {
            id: maximizeButton
            objectName: "maximizeWindowButton"
            x: root.controlsOnLeft ? controlRow.buttonStep * 2
                                   : controlRow.buttonStep
            anchors.verticalCenter: parent.verticalCenter
            tokens: root.tokens
            windowAction: root.maximized ? "restore" : "maximize"
            accessibleDescription: root.maximized
                                   ? qsTr("Restore the Speakr window")
                                   : qsTr("Maximize the Speakr window")
            onActionRequested: function(action) { root.invokeAction(action) }
        }
        ChromeButton {
            id: closeButton
            objectName: "closeWindowButton"
            x: root.controlsOnLeft ? 0 : controlRow.buttonStep * 2
            anchors.verticalCenter: parent.verticalCenter
            tokens: root.tokens
            windowAction: "close"
            accessibleDescription: qsTr("Hide Speakr to the tray; use Quit to stop dictation")
            onActionRequested: function(action) { root.invokeAction(action) }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: root.tokens.borderWidth
        color: root.tokens.border
        Accessible.ignored: true
    }

    Component.onCompleted: Qt.callLater(reportHitRegions)
    onWidthChanged: Qt.callLater(reportHitRegions)
    onHeightChanged: Qt.callLater(reportHitRegions)
    onVisibleChanged: Qt.callLater(reportHitRegions)

    Connections {
        target: root.controller
        enabled: root.controller !== null
        function onCustomChromeEnabledChanged() { Qt.callLater(root.reportHitRegions) }
        function onMaximizedChanged() { Qt.callLater(root.reportHitRegions) }
    }
}
