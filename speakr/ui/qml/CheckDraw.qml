import QtQuick

// One 220 ms check draw (DESIGN.md "Success: one check draw"). The two stroke
// arms scale in sequentially from the elbow so the mark is drawn, not faded.
// Reduced Motion collapses the draw to instant through the motion tokens.
Item {
    id: root
    objectName: "checkDraw"

    required property var tokens
    property bool drawn: false
    property color strokeColor: tokens.accentForeground
    readonly property real strokeWidth: Math.max(2, tokens.metric(2))

    implicitWidth: tokens.metric(16)
    implicitHeight: tokens.metric(16)
    Accessible.ignored: true

    function syncInstant() {
        drawAnimation.stop()
        shortArmScale.xScale = drawn ? 1 : 0
        longArmScale.xScale = drawn ? 1 : 0
    }

    onDrawnChanged: {
        if (drawn) {
            shortArmScale.xScale = 0
            longArmScale.xScale = 0
            drawAnimation.restart()
        } else {
            syncInstant()
        }
    }

    Component.onCompleted: syncInstant()

    Rectangle {
        id: shortArm
        objectName: "checkDrawShortArm"
        x: root.width * 0.14
        y: root.height * 0.55 - root.strokeWidth / 2
        width: root.width * 0.38
        height: root.strokeWidth
        radius: height / 2
        color: root.strokeColor
        rotation: 45
        transformOrigin: Item.Left
        transform: Scale {
            id: shortArmScale
            origin.x: 0
            xScale: 0
        }
    }

    Rectangle {
        id: longArm
        objectName: "checkDrawLongArm"
        x: root.width * 0.40
        y: root.height * 0.81 - root.strokeWidth / 2
        width: root.width * 0.68
        height: root.strokeWidth
        radius: height / 2
        color: root.strokeColor
        rotation: -49
        transformOrigin: Item.Left
        transform: Scale {
            id: longArmScale
            origin.x: 0
            xScale: 0
        }
    }

    SequentialAnimation {
        id: drawAnimation

        NumberAnimation {
            target: shortArmScale
            property: "xScale"
            from: 0
            to: 1
            duration: Math.round(root.tokens.motionEmphasis * 0.4)
            easing.type: Easing.OutQuint
        }
        NumberAnimation {
            target: longArmScale
            property: "xScale"
            from: 0
            to: 1
            duration: Math.round(root.tokens.motionEmphasis * 0.6)
            easing.type: Easing.OutQuint
        }
    }
}
