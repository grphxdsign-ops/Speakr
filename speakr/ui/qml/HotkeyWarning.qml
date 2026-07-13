import QtQuick

InlineNotice {
    id: root

    property string candidate: ""
    readonly property bool risky: isOrdinaryKey(candidate)

    visible: risky
    kind: "warning"
    title: qsTr("Shortcut may conflict")
    message: qsTr("This is an ordinary typing or navigation key. Speakr may start while you use it in another app. Confirm only if that is intentional.")

    function isOrdinaryKey(value) {
        var normalized = String(value).trim().toLowerCase()
        if (normalized.length === 0 || normalized.indexOf("+") >= 0)
            return false
        if (/^[a-z0-9]$/.test(normalized))
            return true
        var ordinary = [
            "space", "spacebar", "tab", "enter", "return", "backspace",
            "delete", "escape", "esc", "left", "right", "up", "down",
            "home", "end", "page up", "page down", "insert"
        ]
        return ordinary.indexOf(normalized) >= 0
    }
}
