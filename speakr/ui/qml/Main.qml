pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    objectName: "mainWindow"

    width: 960
    height: 700
    minimumWidth: 640
    minimumHeight: 520
    visible: false
    title: qsTr("Speakr")
    color: tokens.background
    flags: Qt.Window

    property string currentPage: "home"
    property bool forceOnboarding: false
    readonly property bool showingOnboarding: forceOnboarding
                                               || !Boolean(setting("ui.onboarding_complete", false))
    readonly property bool wideNavigation: width >= tokens.metric(860)
    readonly property var pageNames: ["home", "practice", "vocabulary", "settings", "help"]
    readonly property var pageLabels: [qsTr("Home"), qsTr("Practice"), qsTr("Vocabulary"), qsTr("Settings"), qsTr("Help")]
    readonly property int topNavigationColumns: Math.max(
                                                     1,
                                                     Math.min(
                                                         pageNames.length,
                                                         Math.floor(
                                                             Math.max(1, width - tokens.space24)
                                                             / Math.max(
                                                                 1,
                                                                 Math.round(
                                                                     110 * tokens.textScale)))))
    readonly property int topNavigationRows: Math.ceil(
                                                  pageNames.length
                                                  / Math.max(1, topNavigationColumns))

    function setting(path, fallbackValue) {
        var source = bridge.settings || ({})
        if (source[path] !== undefined && source[path] !== null)
            return source[path]
        var parts = path.split(".")
        for (var i = 0; i < parts.length; ++i) {
            if (source === null || source === undefined || source[parts[i]] === undefined)
                return fallbackValue
            source = source[parts[i]]
        }
        return source === undefined ? fallbackValue : source
    }

    function pageIndex(page) {
        var index = pageNames.indexOf(page)
        return index < 0 ? 0 : index
    }

    function numericSetting(path, fallbackValue) {
        var result = Number(setting(path, fallbackValue))
        return isFinite(result) ? result : Number(fallbackValue)
    }

    function motionPreference() {
        var result = setting("ui.reduced_motion", setting("ui.motion", "system"))
        if (result === true || String(result) === "reduce") return "reduced"
        return String(result)
    }

    function go(page) {
        if (currentPage === "practice" && page !== "practice") {
            bridge.stopPractice()
            bridge.clearPractice()
        }
        currentPage = pageNames.indexOf(page) >= 0 ? page : "home"
        pageTransition.restart()
        bridge.navigate(currentPage)
        Qt.callLater(function() { focusCurrentPage() })
    }

    function focusCurrentPage() {
        if (currentPage === "home") homePage.focusHeading()
        else if (currentPage === "practice") practicePage.focusHeading()
        else if (currentPage === "vocabulary") vocabularyPage.focusHeading()
        else if (currentPage === "settings") settingsPage.focusHeading()
        else if (currentPage === "help") helpPage.focusHeading()
    }

    function beginRepeatSetup() {
        if (currentPage === "practice") {
            bridge.stopPractice()
            bridge.clearPractice()
        }
        forceOnboarding = true
    }

    Theme {
        id: tokens
        mode: String(root.setting("ui.theme", "system"))
        density: String(root.setting("ui.density", "comfortable"))
        textScale: Math.max(1.0, Math.min(2.0, root.numericSetting("ui.text_scale", 100) / 100.0))
        reduceMotion: root.motionPreference() === "reduced"
                      || (root.motionPreference() === "system"
                          && Boolean(root.setting("ui.system_reduced_motion",
                                                  root.setting("system_reduced_motion", false))))
        systemHighContrast: Boolean(root.setting("ui.system_high_contrast",
                                                 root.setting("system_high_contrast", false)))
    }

    palette.window: tokens.background
    palette.windowText: tokens.text
    palette.base: tokens.surface
    palette.alternateBase: tokens.surfaceRaised
    palette.text: tokens.text
    palette.button: tokens.surface
    palette.buttonText: tokens.text
    palette.highlight: tokens.accent
    palette.highlightedText: tokens.accentText

    Shortcut {
        sequence: StandardKey.Quit
        onActivated: bridge.quitApp()
    }

    Shortcut {
        sequence: "Ctrl+1"
        enabled: !root.showingOnboarding
        onActivated: root.go("home")
    }
    Shortcut {
        sequence: "Ctrl+2"
        enabled: !root.showingOnboarding
        onActivated: root.go("practice")
    }
    Shortcut {
        sequence: "Ctrl+3"
        enabled: !root.showingOnboarding
        onActivated: root.go("vocabulary")
    }
    Shortcut {
        sequence: "Ctrl+4"
        enabled: !root.showingOnboarding
        onActivated: root.go("settings")
    }
    Shortcut {
        sequence: "Ctrl+5"
        enabled: !root.showingOnboarding
        onActivated: root.go("help")
    }
    Shortcut {
        sequence: "Escape"
        enabled: bridge.capturingHotkey
        onActivated: bridge.cancelHotkeyCapture()
    }

    onClosing: function(closeEvent) {
        bridge.stopPractice()
        bridge.clearPractice()
        if (bridge.quitting) {
            closeEvent.accepted = true
        } else {
            closeEvent.accepted = false
            root.hide()
        }
    }

    onVisibilityChanged: {
        if (visibility === Window.Hidden || visibility === Window.Minimized) {
            bridge.stopPractice()
            bridge.clearPractice()
        }
    }

    Component.onCompleted: {
        if (root.showingOnboarding
                || Boolean(root.setting("ui.open_window_on_start", true))) {
            root.show()
            Qt.callLater(function() {
                if (!root.showingOnboarding) root.focusCurrentPage()
            })
        }
    }

    header: Rectangle {
        implicitHeight: Math.max(tokens.metric(64), headerContent.implicitHeight + tokens.space16)
        color: tokens.surface
        border.width: 0

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: tokens.border
        }

        GridLayout {
            id: headerContent
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: tokens.space24
            anchors.rightMargin: tokens.space24
            columns: width >= tokens.metric(560) ? 2 : 1
            columnSpacing: tokens.space24
            rowSpacing: tokens.space4

            RowLayout {
                Layout.fillWidth: true
                spacing: tokens.space12

                RowLayout {
                    spacing: tokens.space4
                    Accessible.role: Accessible.Graphic
                    Accessible.name: qsTr("Speakr signal path")

                    Repeater {
                        model: 3
                        Rectangle {
                            required property int index
                            implicitWidth: tokens.metric(index === 1 ? 10 : 8)
                            implicitHeight: implicitWidth
                            Layout.preferredWidth: implicitWidth
                            Layout.preferredHeight: implicitHeight
                            radius: implicitWidth / 2
                            color: index === 1 ? tokens.accent : tokens.text
                        }
                    }
                }

                PlainText {
                    text: qsTr("Speakr")
                    color: tokens.text
                    font.family: tokens.fontFamily
                    font.pixelSize: tokens.sectionHeading
                    font.weight: Font.DemiBold
                    Accessible.role: Accessible.Heading
                    Accessible.name: text
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.alignment: root.wideNavigation ? Qt.AlignRight : Qt.AlignLeft
                spacing: tokens.space8
                Accessible.role: Accessible.Note
                Accessible.name: qsTr("Everything stays on this device")

                Rectangle {
                    implicitWidth: tokens.metric(10)
                    implicitHeight: implicitWidth
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    radius: implicitWidth / 2
                    color: tokens.success
                }

                PlainText {
                    Layout.fillWidth: true
                    text: qsTr("Everything stays on this device")
                    color: tokens.text
                    font.family: tokens.fontFamily
                    font.pixelSize: tokens.secondary
                    font.weight: Font.Medium
                    wrapMode: Text.Wrap
                }
            }
        }
    }

    StackLayout {
        anchors.fill: parent
        currentIndex: root.showingOnboarding ? 0 : 1
        Accessible.role: Accessible.Application
        Accessible.name: qsTr("Speakr private dictation")
        Accessible.description: qsTr("Local voice dictation settings and status")

        OnboardingPage {
            tokens: tokens
            appState: bridge.state
            settings: bridge.settings
            practice: bridge.practice
            onCompleted: {
                root.forceOnboarding = false
                root.go("home")
            }
        }

        GridLayout {
            columns: root.wideNavigation ? 2 : 1
            rows: root.wideNavigation ? 1 : 2
            columnSpacing: 0
            rowSpacing: 0

            Loader {
                Layout.fillHeight: root.wideNavigation
                Layout.fillWidth: !root.wideNavigation
                Layout.maximumWidth: root.width
                Layout.preferredWidth: root.wideNavigation ? tokens.metric(210) : -1
                Layout.preferredHeight: root.wideNavigation
                                        ? -1
                                        : root.topNavigationRows * tokens.controlHeight
                                          + (root.topNavigationRows - 1) * tokens.space4
                                          + tokens.space16
                sourceComponent: root.wideNavigation ? sideNavigation : topNavigation
            }

            Rectangle {
                id: contentPanel
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: tokens.background
                transform: Translate { id: contentShift; x: 0 }

                StackLayout {
                    anchors.fill: parent
                    currentIndex: root.pageIndex(root.currentPage)

                    HomePage {
                        id: homePage
                        tokens: tokens
                        appState: bridge.state
                        settings: bridge.settings
                        onNavigateRequested: function(page) { root.go(page) }
                    }

                    PracticePage {
                        id: practicePage
                        tokens: tokens
                        practice: bridge.practice
                        appState: bridge.state
                        onNavigateRequested: function(page) { root.go(page) }
                    }

                    VocabularyPage {
                        id: vocabularyPage
                        tokens: tokens
                        appState: bridge.state
                        manualWords: bridge.manualWords
                        learnedWords: bridge.learnedWords
                    }

                    SettingsPage {
                        id: settingsPage
                        tokens: tokens
                        settings: bridge.settings
                        appState: bridge.state
                    }

                    HelpPage {
                        id: helpPage
                        tokens: tokens
                        appState: bridge.state
                        settings: bridge.settings
                        onRepeatSetupRequested: root.beginRepeatSetup()
                    }
                }
            }
        }
    }

    ParallelAnimation {
        id: pageTransition
        NumberAnimation {
            target: contentPanel
            property: "opacity"
            from: tokens.reduceMotion ? 1 : 0
            to: 1
            duration: tokens.motionStandard
            easing.type: Easing.OutQuint
        }
        NumberAnimation {
            target: contentShift
            property: "x"
            from: tokens.reduceMotion ? 0 : tokens.metric(8)
            to: 0
            duration: tokens.motionStandard
            easing.type: Easing.OutQuint
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: bridge.quitting
        z: 100
        color: tokens.withAlpha(tokens.background, 0.94)
        Accessible.role: Accessible.AlertMessage
        Accessible.name: qsTr("Quitting Speakr")

        ColumnLayout {
            anchors.centerIn: parent
            spacing: tokens.space12

            PlainText {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Closing local services")
                color: tokens.text
                font.family: tokens.fontFamily
                font.pixelSize: tokens.statusHeading
                font.weight: Font.DemiBold
            }

            PlainText {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Audio buffers and temporary Practice text are being cleared.")
                color: tokens.mutedText
                font.family: tokens.fontFamily
                font.pixelSize: tokens.body
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }
        }
    }

    Component {
        id: sideNavigation

        Rectangle {
            color: tokens.surface
            border.width: 0

            Rectangle {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: 1
                color: tokens.border
            }

            ColumnLayout {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: tokens.space12
                spacing: tokens.space4
                Accessible.role: Accessible.PageTabList
                Accessible.name: qsTr("Main navigation")

                Repeater {
                    model: root.pageNames

                    delegate: NavigationButton {
                        required property int index
                        required property string modelData
                        Layout.fillWidth: true
                        tokens: tokens
                        text: root.pageLabels[index]
                        selected: root.currentPage === modelData
                        Accessible.description: qsTr("Open %1, shortcut Control %2")
                                                .arg(root.pageLabels[index]).arg(index + 1)
                        onClicked: root.go(modelData)
                    }
                }
            }
        }
    }

    Component {
        id: topNavigation

        Rectangle {
            implicitHeight: navigationGrid.implicitHeight + tokens.space16
            color: tokens.surface
            border.width: 0

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: tokens.border
            }

            GridLayout {
                id: navigationGrid
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: tokens.space12
                anchors.rightMargin: tokens.space12
                columns: root.topNavigationColumns
                columnSpacing: tokens.space4
                rowSpacing: tokens.space4
                Accessible.role: Accessible.PageTabList
                Accessible.name: qsTr("Main navigation")

                Repeater {
                    model: root.pageNames

                    delegate: NavigationButton {
                        required property int index
                        required property string modelData
                        Layout.fillWidth: true
                        tokens: tokens
                        text: root.pageLabels[index]
                        selected: root.currentPage === modelData
                        Accessible.description: qsTr("Open %1, shortcut Control %2")
                                                .arg(root.pageLabels[index]).arg(index + 1)
                        onClicked: root.go(modelData)
                    }
                }
            }
        }
    }
}
