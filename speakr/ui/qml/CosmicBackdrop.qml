import QtQuick

Item {
    id: root

    required property var tokens
    property bool paintCanvas: true

    clip: true
    Accessible.ignored: true

    Rectangle {
        anchors.fill: parent
        color: root.paintCanvas ? root.tokens.canvas : "transparent"
    }

    // These fields are static local geometry. They never sample the desktop,
    // invoke a shader, or repaint on a timer.
    Rectangle {
        visible: root.tokens.effectTier !== "off"
        width: Math.max(root.width * 0.58, root.tokens.metric(300))
        height: width
        radius: width / 2
        x: -width * 0.28
        y: -height * 0.40
        color: root.tokens.atmosphereViolet
    }

    Rectangle {
        visible: root.tokens.effectTier !== "off"
        width: Math.max(root.width * 0.44, root.tokens.metric(240))
        height: width
        radius: width / 2
        x: root.width - width * 0.64
        y: root.height - height * 0.58
        color: root.tokens.atmosphereCyan
    }

    Rectangle {
        visible: root.tokens.effectTier === "full"
        width: Math.max(root.width * 0.30, root.tokens.metric(180))
        height: width
        radius: width / 2
        x: root.width * 0.54
        y: -height * 0.38
        color: root.tokens.atmosphereBlush
    }

    Rectangle {
        visible: root.tokens.effectTier !== "off"
        width: Math.max(root.width * 0.68, root.tokens.metric(400))
        height: Math.max(root.height * 0.72, root.tokens.metric(300))
        radius: Math.min(width, height) / 2
        x: root.width * 0.37
        y: root.height * 0.04
        color: "transparent"
        border.width: 1
        border.color: root.tokens.orbitLine
        rotation: -14
    }

    Rectangle {
        visible: root.tokens.effectTier === "full"
        width: Math.max(root.width * 0.52, root.tokens.metric(320))
        height: Math.max(root.height * 0.50, root.tokens.metric(220))
        radius: Math.min(width, height) / 2
        x: -width * 0.18
        y: root.height * 0.52
        color: "transparent"
        border.width: 1
        border.color: root.tokens.orbitLine
        rotation: 10
    }
}
