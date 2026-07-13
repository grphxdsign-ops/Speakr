pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

Item {
    id: root

    required property var tokens
    property var controller: null
    property var hostWindow: null
    readonly property bool controlsOnLeft: Qt.platform.os === "osx"
    readonly property bool compactPrivacyCue: width < tokens.metric(720)
                                               || tokens.textScale > 1.5
    readonly property bool maximized: controller !== null && Boolean(controller.maximized)
    readonly property var firstControl: controlRow.firstControl
    readonly property var lastControl: controlRow.lastControl

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
        if (controlRow.minimizeButton === null
                || controlRow.maximizeButton === null
                || controlRow.closeButton === null) return
        controller.setHitRegions(sceneRect(dragRegion),
                                 sceneRect(controlRow.minimizeButton),
                                 sceneRect(controlRow.maximizeButton),
                                 sceneRect(controlRow.closeButton),
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
        spacing: root.compactPrivacyCue ? root.tokens.space8
                                        : root.tokens.space16

        RowLayout {
            spacing: root.tokens.space8
            Accessible.role: Accessible.Graphic
            Accessible.name: qsTr("Speakr signal path")

            RowLayout {
                spacing: root.tokens.space4
                Repeater {
                    model: 3
                    Rectangle {
                        objectName: "chromeSignalNode"
                        required property int index
                        Layout.preferredWidth: root.tokens.metric(index === 1 ? 10 : 8)
                        Layout.preferredHeight: Layout.preferredWidth
                        radius: width / 2
                        color: index === 1 ? root.tokens.accentForeground
                                           : root.tokens.text
                        Accessible.ignored: true
                    }
                }
            }

            PlainText {
                text: qsTr("Speakr")
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.compactPrivacyCue
                                ? root.tokens.statusHeading
                                : root.tokens.sectionHeading
                font.weight: Font.DemiBold
                Accessible.ignored: true
            }
        }

        Item { Layout.fillWidth: true }

        RowLayout {
            id: privacyCue
            objectName: "windowPrivacyCue"
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
                objectName: "windowPrivacyCueText"
                text: root.compactPrivacyCue
                      ? qsTr("Local only")
                      : qsTr("Everything stays on this device")
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
        readonly property real buttonWidth: root.tokens.controlHeight
        readonly property real buttonStep: buttonWidth + root.tokens.space4
        readonly property var firstControl: firstControlLoader.item
        readonly property var lastControl: lastControlLoader.item
        readonly property var minimizeButton: root.controlsOnLeft
                                              ? middleControlLoader.item
                                              : firstControlLoader.item
        readonly property var maximizeButton: root.controlsOnLeft
                                              ? lastControlLoader.item
                                              : middleControlLoader.item
        readonly property var closeButton: root.controlsOnLeft
                                           ? firstControlLoader.item
                                           : lastControlLoader.item
        implicitWidth: buttonWidth * 3 + root.tokens.space8
        implicitHeight: buttonWidth
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: root.controlsOnLeft ? parent.left : undefined
        anchors.right: root.controlsOnLeft ? undefined : parent.right
        anchors.leftMargin: root.tokens.space8
        anchors.rightMargin: root.tokens.space8
        Accessible.role: Accessible.Grouping
        Accessible.name: qsTr("Window controls")

        Loader {
            id: firstControlLoader
            x: 0
            anchors.verticalCenter: parent.verticalCenter
            sourceComponent: root.controlsOnLeft ? closeControl : minimizeControl
        }
        Loader {
            id: middleControlLoader
            x: controlRow.buttonStep
            anchors.verticalCenter: parent.verticalCenter
            sourceComponent: root.controlsOnLeft ? minimizeControl : maximizeControl
        }
        Loader {
            id: lastControlLoader
            x: controlRow.buttonStep * 2
            anchors.verticalCenter: parent.verticalCenter
            sourceComponent: root.controlsOnLeft ? maximizeControl : closeControl
        }
    }

    Component {
        id: minimizeControl

        ChromeButton {
            objectName: "minimizeWindowButton"
            tokens: root.tokens
            windowAction: "minimize"
            accessibleDescription: qsTr("Minimize Speakr to the taskbar or Dock")
            KeyNavigation.tab: controlRow.maximizeButton
            KeyNavigation.backtab: root.controlsOnLeft
                                   ? controlRow.closeButton : null
            onActionRequested: function(action) { root.invokeAction(action) }
        }
    }

    Component {
        id: maximizeControl

        ChromeButton {
            objectName: "maximizeWindowButton"
            tokens: root.tokens
            windowAction: root.maximized ? "restore" : "maximize"
            accessibleDescription: root.maximized
                                   ? qsTr("Restore the Speakr window")
                                   : qsTr("Maximize the Speakr window")
            KeyNavigation.tab: root.controlsOnLeft
                               ? null : controlRow.closeButton
            KeyNavigation.backtab: controlRow.minimizeButton
            onActionRequested: function(action) { root.invokeAction(action) }
        }
    }

    Component {
        id: closeControl

        ChromeButton {
            objectName: "closeWindowButton"
            tokens: root.tokens
            windowAction: "close"
            accessibleDescription: qsTr("Hide Speakr to the tray; use Quit to stop dictation")
            KeyNavigation.tab: root.controlsOnLeft
                               ? controlRow.minimizeButton : null
            KeyNavigation.backtab: root.controlsOnLeft
                                   ? null : controlRow.maximizeButton
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
