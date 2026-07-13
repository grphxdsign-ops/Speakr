import QtQuick

Item {
    id: root

    required property var tokens
    property string role: "major" // shell | navigation | major | notice | content | hud
    property int cornerRadius: role === "shell" ? tokens.radiusShell
                                                  : (role === "major" ? tokens.radiusPanel
                                                                      : tokens.radiusControl)
    property int padding: tokens.space16
    property bool elevated: role === "shell" || role === "major"
    property bool showEdge: true
    property color fillColor: tokens.materialColor(role)
    property color edgeColor: tokens.border
    default property alias contentData: content.data
    property alias contentItem: content

    implicitWidth: tokens.metric(240)
    implicitHeight: tokens.metric(120)

    Rectangle {
        visible: root.elevated && root.tokens.effectTier !== "off"
        x: 0
        y: root.tokens.metric(2)
        width: root.width
        height: root.height
        radius: root.cornerRadius
        color: root.tokens.shadow
        Accessible.ignored: true
    }

    Rectangle {
        anchors.fill: parent
        radius: root.cornerRadius
        color: root.fillColor
        border.width: root.showEdge ? root.tokens.borderWidth : 0
        border.color: root.edgeColor
        Accessible.ignored: true
    }

    Item {
        id: content
        anchors.fill: parent
        anchors.margins: root.padding
    }
}
