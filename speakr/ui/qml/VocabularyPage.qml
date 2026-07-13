pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: root
    objectName: "vocabularyPage"

    required property var tokens
    // The process-owned Bridge is intentionally supplied as a QML context
    // property so the page keeps the same narrow controller contract as Main.
    // qmllint disable unqualified
    readonly property var uiBridge: bridge
    // qmllint enable unqualified
    property var appState: ({})
    property var manualWords: []
    property var learnedWords: []
    property int tabIndex: 0
    property string pendingAction: ""
    property string pendingTarget: ""
    property string pendingId: ""
    property bool reloadFailed: false
    property int focusScrollGeneration: 0
    readonly property int pageMargin: width < tokens.metric(760)
                                      ? tokens.space16 : tokens.space32
    readonly property int manualWordCount: manualList(false).length
    readonly property int replacementCount: manualList(true).length
    readonly property int learnedWordCount: (learnedWords || []).length

    function focusHeading() {
        pageHeading.forceActiveFocus(Qt.OtherFocusReason)
    }

    function field(item, key, fallbackValue) {
        if (item !== null && item !== undefined && typeof item === "object"
                && item[key] !== null && item[key] !== undefined)
            return item[key]
        return fallbackValue
    }

    function setField(item, key, value) {
        if (item !== null && item !== undefined && typeof item === "object")
            item[key] = value
    }

    function isReplacement(item) {
        if (typeof item !== "object" || item === null)
            return false
        return field(item, "kind", "") === "replacement"
                || (String(field(item, "heard", "")).length > 0
                    && String(field(item, "intended", "")).length > 0)
    }

    function manualList(replacements) {
        var result = []
        var source = manualWords || []
        for (var i = 0; i < source.length; ++i) {
            if (isReplacement(source[i]) === replacements)
                result.push(source[i])
        }
        return result
    }

    function wordText(item) {
        if (typeof item === "string") return item
        return String(field(item, "word", field(item, "text", "")))
    }

    function rowId(item) {
        if (typeof item === "string") return item
        return String(field(item, "id", field(item, "line", wordText(item))))
    }

    function learnedDetail(item) {
        var count = Number(field(item, "count", 1))
        var recency = String(field(item, "last_seen", ""))
        if (recency.length > 0)
            return qsTr("Seen %1 times \u00b7 Last seen %2").arg(count).arg(recency)
        return qsTr("Seen %1 times").arg(count)
    }

    function requestDestructiveAction(action, target, idValue) {
        pendingAction = action
        pendingTarget = target
        pendingId = idValue
        confirmDialog.open()
    }

    function confirmDestructiveAction() {
        if (pendingAction === "manual")
            root.uiBridge.removeManualWord(pendingId)
        else if (pendingAction === "learned")
            root.uiBridge.forgetLearnedWord(pendingTarget)
        confirmDialog.close()
    }

    function issue() {
        return field(appState, "last_issue", null)
    }

    function issueCode() {
        return String(field(issue(), "code", ""))
    }

    function vocabularyIssueVisible() {
        return ["busy_setting", "dictionary_invalid", "dictionary_changed",
                "vocabulary_save_failed"].indexOf(issueCode()) >= 0
    }

    function issueKind() {
        return issueCode() === "busy_setting" ? "warning" : "danger"
    }

    function issueTitle() {
        if (issueCode() === "busy_setting")
            return qsTr("Vocabulary is temporarily paused")
        if (issueCode() === "dictionary_invalid")
            return qsTr("This entry needs attention")
        if (issueCode() === "dictionary_changed")
            return qsTr("The dictionary changed outside Speakr")
        return qsTr("Vocabulary was not saved")
    }

    function issueDetail() {
        if (issueCode() === "busy_setting")
            return qsTr("Finish the current local dictation or Practice result, then try again. Typed input stays here.")
        if (issueCode() === "dictionary_changed")
            return qsTr("Reload the local file before removing an entry. Speakr uses content-bound entry identities so a different line cannot be removed by mistake.")
        if (issueCode() === "dictionary_invalid")
            return qsTr("Correct the typed value or inspect the local dictionary file. Typed input stays here.")
        return qsTr("The local file remains unchanged. Typed input stays here so you can retry.")
    }

    function issueActionLabel() {
        var action = String(field(issue(), "action", ""))
        if (action === "open_dictionary" || action === "edit_vocabulary")
            return qsTr("Open dictionary file")
        if (action === "reload_dictionary")
            return qsTr("Reload from file")
        return qsTr("Dismiss")
    }

    function runIssueAction() {
        var action = String(field(issue(), "action", ""))
        if (action === "open_dictionary" || action === "edit_vocabulary") {
            root.uiBridge.openLocal("dictionary")
            return true
        }
        if (action === "reload_dictionary")
            return reloadVocabulary()
        root.uiBridge.dismissIssue()
        return true
    }

    function reloadVocabulary() {
        reloadFailed = !Boolean(root.uiBridge.reloadLocalState())
        return !reloadFailed
    }

    function submitWord() {
        var word = newWord.text.trim()
        if (word.length > 0 && root.uiBridge.addWord(word)) {
            newWord.clear()
            return true
        }
        return false
    }

    function submitReplacement() {
        var heard = newHeard.text.trim()
        var intended = newIntended.text.trim()
        if (heard.length > 0 && intended.length > 0
                && root.uiBridge.addReplacement(heard, intended)) {
            newHeard.clear()
            newIntended.clear()
            return true
        }
        return false
    }

    function isPageDescendant(item) {
        var current = item
        while (current !== null && current !== undefined) {
            if (current === root) return true
            current = current.parent
        }
        return false
    }

    function ensureFocusedItemVisible(item) {
        if (!isPageDescendant(item)) return
        var viewport = scroll.contentItem
        if (viewport === null || viewport === undefined
                || field(viewport, "contentY", undefined) === undefined) return
        var mapped = item.mapToItem(viewport, 0, 0)
        var margin = root.tokens.space12
        var top = Number(mapped.y)
        var bottom = top + Number(item.height)
        var viewportHeight = Number(viewport.height)
        var originY = Number(field(viewport, "originY", 0))
        var contentHeight = Math.max(viewportHeight,
                                     Number(field(viewport, "contentHeight", 0)))
        var maximumY = originY + Math.max(0, contentHeight - viewportHeight)
        var nextY = Number(field(viewport, "contentY", 0))
        if (top < margin)
            nextY += top - margin
        else if (bottom > viewportHeight - margin)
            nextY += bottom - viewportHeight + margin
        setField(viewport, "contentY",
                 Math.max(originY, Math.min(maximumY, nextY)))
    }

    function queueFocusedItemVisibility(item) {
        focusScrollGeneration += 1
        var generation = focusScrollGeneration
        Qt.callLater(function() {
            if (generation !== root.focusScrollGeneration) return
            root.ensureFocusedItemVisible(item)
            Qt.callLater(function() {
                if (generation === root.focusScrollGeneration)
                    root.ensureFocusedItemVisible(item)
            })
        })
    }

    Connections {
        target: root.Window.window
        enabled: target !== null

        function onActiveFocusItemChanged() {
            var window = root.Window.window
            if (window !== null && root.isPageDescendant(window.activeFocusItem))
                root.queueFocusedItemVisibility(window.activeFocusItem)
        }
    }

    ScrollView {
        id: scroll
        objectName: "vocabularyScroll"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        Column {
            width: scroll.contentWidth
            spacing: root.tokens.space16

            Item {
                width: parent.width
                height: root.tokens.space8
            }

            GlassSurface {
                id: heroSurface
                objectName: "vocabularyHeroSurface"
                x: root.pageMargin
                width: Math.max(0, parent.width - root.pageMargin * 2)
                implicitHeight: heroContent.implicitHeight + padding * 2
                tokens: root.tokens
                role: "major"
                padding: root.tokens.space24

                GridLayout {
                    id: heroContent
                    anchors.fill: parent
                    columns: width >= root.tokens.metric(620) ? 2 : 1
                    columnSpacing: root.tokens.space24
                    rowSpacing: root.tokens.space16

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: root.tokens.space8

                        PlainText {
                            id: pageHeading
                            objectName: "vocabularyPageHeading"
                            Layout.fillWidth: true
                            text: qsTr("Vocabulary")
                            color: root.tokens.text
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.pageHeading
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                            Accessible.role: Accessible.Heading
                            Accessible.name: text
                        }

                        PlainText {
                            Layout.fillWidth: true
                            text: qsTr("Teach Speakr names, exact phrase corrections, and useful local terms.")
                            color: root.tokens.mutedText
                            font.family: root.tokens.fontFamily
                            font.pixelSize: root.tokens.body
                            wrapMode: Text.Wrap
                        }
                    }

                    StatusOrb {
                        objectName: "vocabularySummaryStatus"
                        Layout.fillWidth: true
                        tokens: root.tokens
                        statusKind: "active"
                        symbol: "\u2022"
                        label: qsTr("Stored only on this device")
                        description: qsTr("%1 manual words, %2 replacements, and %3 learned words")
                                     .arg(root.manualWordCount)
                                     .arg(root.replacementCount)
                                     .arg(root.learnedWordCount)
                    }
                }
            }

            InlineNotice {
                id: issueNotice
                objectName: "vocabularyIssueNotice"
                x: root.pageMargin
                width: Math.max(0, parent.width - root.pageMargin * 2)
                visible: root.vocabularyIssueVisible()
                tokens: root.tokens
                kind: root.issueKind()
                title: root.issueTitle()
                message: String(root.field(root.issue(), "message", ""))
                detail: root.issueDetail()
                actionText: root.issueActionLabel()
                actionDescription: qsTr("Perform the recommended local Vocabulary recovery action")
                onActionRequested: root.runIssueAction()
            }

            InlineNotice {
                objectName: "vocabularyReloadFailure"
                x: root.pageMargin
                width: Math.max(0, parent.width - root.pageMargin * 2)
                visible: root.reloadFailed
                tokens: root.tokens
                kind: "danger"
                title: qsTr("Vocabulary could not be reloaded")
                message: qsTr("The current on-screen entries remain available.")
                detail: qsTr("Check the local dictionary file, then try again.")
                actionText: qsTr("Try reload again")
                actionDescription: qsTr("Retry loading the local dictionary file")
                onActionRequested: root.reloadVocabulary()
            }

            GlassSurface {
                objectName: "vocabularySectionNavigation"
                x: root.pageMargin
                width: Math.max(0, parent.width - root.pageMargin * 2)
                implicitHeight: sectionNavigation.implicitHeight + padding * 2
                tokens: root.tokens
                role: "navigation"
                padding: root.tokens.space12
                elevated: false

                GridLayout {
                    id: sectionNavigation
                    anchors.fill: parent
                    columns: width >= root.tokens.metric(620) ? 3 : 1
                    columnSpacing: root.tokens.space8
                    rowSpacing: root.tokens.space8
                    Accessible.role: Accessible.PageTabList
                    Accessible.name: qsTr("Vocabulary sections")

                    NavigationButton {
                        objectName: "manualWordsTab"
                        Layout.fillWidth: true
                        tokens: root.tokens
                        text: qsTr("Manual words (%1)").arg(root.manualWordCount)
                        selected: root.tabIndex === 0
                        Accessible.description: qsTr("Words you explicitly added")
                        onClicked: root.tabIndex = 0
                    }

                    NavigationButton {
                        objectName: "replacementsTab"
                        Layout.fillWidth: true
                        tokens: root.tokens
                        text: qsTr("Replacements (%1)").arg(root.replacementCount)
                        selected: root.tabIndex === 1
                        Accessible.description: qsTr("Exact heard-to-intended phrase replacements")
                        onClicked: root.tabIndex = 1
                    }

                    NavigationButton {
                        objectName: "learnedWordsTab"
                        Layout.fillWidth: true
                        tokens: root.tokens
                        text: qsTr("Learned words (%1)").arg(root.learnedWordCount)
                        selected: root.tabIndex === 2
                        Accessible.description: qsTr("Words learned from local dictation")
                        onClicked: root.tabIndex = 2
                    }
                }
            }

            GlassSurface {
                id: contentSurface
                objectName: "vocabularyContentSurface"
                x: root.pageMargin
                width: Math.max(0, parent.width - root.pageMargin * 2)
                implicitHeight: contentStack.implicitHeight + padding * 2
                tokens: root.tokens
                role: "content"
                padding: root.tokens.space24
                elevated: false

                StackLayout {
                    id: contentStack
                    anchors.fill: parent
                    currentIndex: root.tabIndex

                    ColumnLayout {
                        spacing: root.tokens.space16

                        SectionHeading {
                            Layout.fillWidth: true
                            tokens: root.tokens
                            title: qsTr("Manual words")
                            description: qsTr("Add names and specialized terms that should keep their spelling.")
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: width >= root.tokens.metric(560) ? 2 : 1
                            columnSpacing: root.tokens.space12
                            rowSpacing: root.tokens.space8

                            QuietTextField {
                                id: newWord
                                objectName: "newManualWordField"
                                Layout.fillWidth: true
                                tokens: root.tokens
                                placeholderText: qsTr("Name or specialized word")
                                accessibleName: qsTr("New manual word")
                                accessibleDescription: qsTr("The value remains here if it cannot be saved")
                                onAccepted: root.submitWord()
                            }

                            QuietButton {
                                id: addWord
                                objectName: "addManualWordButton"
                                Layout.fillWidth: contentStack.width < root.tokens.metric(560)
                                tokens: root.tokens
                                text: qsTr("Add word")
                                kind: "primary"
                                enabled: newWord.text.trim().length > 0
                                accessibleDescription: qsTr("Add this spelling to the local manual vocabulary")
                                onClicked: root.submitWord()
                            }
                        }

                        InlineNotice {
                            objectName: "manualWordsEmptyState"
                            Layout.fillWidth: true
                            visible: root.manualWordCount === 0
                            tokens: root.tokens
                            kind: "info"
                            title: qsTr("No manual words yet")
                            message: qsTr("Add a name, product, place, or specialized term that speech models often miss.")
                        }

                        ColumnLayout {
                            objectName: "manualWordsList"
                            Layout.fillWidth: true
                            spacing: root.tokens.space8
                            Accessible.role: Accessible.Grouping
                            Accessible.name: qsTr("Manual word entries")

                            Repeater {
                                model: root.manualList(false)

                                delegate: GlassSurface {
                                    id: manualEntry
                                    required property var modelData
                                    readonly property string entryId: root.rowId(manualEntry.modelData)
                                    objectName: "manualWordRow_" + entryId
                                    Layout.fillWidth: true
                                    implicitHeight: manualWordRow.implicitHeight + padding * 2
                                    tokens: root.tokens
                                    role: "notice"
                                    padding: root.tokens.space12
                                    elevated: false
                                    Accessible.role: Accessible.Grouping
                                    Accessible.name: qsTr("Manual word: %1").arg(root.wordText(manualEntry.modelData))

                                    GridLayout {
                                        id: manualWordRow
                                        anchors.fill: parent
                                        columns: width >= root.tokens.metric(500) ? 2 : 1
                                        columnSpacing: root.tokens.space12
                                        rowSpacing: root.tokens.space8

                                        PlainText {
                                            Layout.fillWidth: true
                                            text: root.wordText(manualEntry.modelData)
                                            color: root.tokens.text
                                            font.family: root.tokens.fontFamily
                                            font.pixelSize: root.tokens.body
                                            font.weight: Font.Medium
                                            wrapMode: Text.Wrap
                                            Accessible.ignored: true
                                        }

                                        QuietButton {
                                            objectName: "removeManualButton_" + manualEntry.entryId
                                            Layout.fillWidth: manualWordRow.columns === 1
                                            tokens: root.tokens
                                            text: qsTr("Remove")
                                            kind: "danger"
                                            accessibleDescription: qsTr("Ask before removing %1 from manual words")
                                                                   .arg(root.wordText(manualEntry.modelData))
                                            onClicked: root.requestDestructiveAction(
                                                           "manual",
                                                           root.wordText(manualEntry.modelData),
                                                           manualEntry.entryId)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: root.tokens.space16

                        SectionHeading {
                            Layout.fillWidth: true
                            tokens: root.tokens
                            title: qsTr("Replacements")
                            description: qsTr("Use one exact correction whenever the same phrase is misheard.")
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: width >= root.tokens.metric(620) ? 3 : 1
                            columnSpacing: root.tokens.space12
                            rowSpacing: root.tokens.space8

                            QuietTextField {
                                id: newHeard
                                objectName: "newReplacementHeardField"
                                Layout.fillWidth: true
                                tokens: root.tokens
                                placeholderText: qsTr("What Speakr heard")
                                accessibleName: qsTr("Heard phrase")
                                accessibleDescription: qsTr("The value remains here if it cannot be saved")
                            }

                            QuietTextField {
                                id: newIntended
                                objectName: "newReplacementIntendedField"
                                Layout.fillWidth: true
                                tokens: root.tokens
                                placeholderText: qsTr("What you intended")
                                accessibleName: qsTr("Intended phrase")
                                accessibleDescription: qsTr("The value remains here if it cannot be saved")
                                onAccepted: root.submitReplacement()
                            }

                            QuietButton {
                                id: addReplacement
                                objectName: "addReplacementButton"
                                Layout.fillWidth: contentStack.width < root.tokens.metric(620)
                                tokens: root.tokens
                                text: qsTr("Add replacement")
                                kind: "primary"
                                enabled: newHeard.text.trim().length > 0
                                         && newIntended.text.trim().length > 0
                                accessibleDescription: qsTr("Add this exact phrase correction locally")
                                onClicked: root.submitReplacement()
                            }
                        }

                        InlineNotice {
                            objectName: "replacementsEmptyState"
                            Layout.fillWidth: true
                            visible: root.replacementCount === 0
                            tokens: root.tokens
                            kind: "info"
                            title: qsTr("No replacements yet")
                            message: qsTr("Add one when a recurring mishearing should always become the same intended phrase.")
                        }

                        ColumnLayout {
                            objectName: "replacementsList"
                            Layout.fillWidth: true
                            spacing: root.tokens.space8
                            Accessible.role: Accessible.Grouping
                            Accessible.name: qsTr("Replacement entries")

                            Repeater {
                                model: root.manualList(true)

                                delegate: GlassSurface {
                                    id: replacementEntry
                                    required property var modelData
                                    readonly property string entryId: root.rowId(replacementEntry.modelData)
                                    objectName: "replacementRow_" + entryId
                                    Layout.fillWidth: true
                                    implicitHeight: replacementRow.implicitHeight + padding * 2
                                    tokens: root.tokens
                                    role: "notice"
                                    padding: root.tokens.space12
                                    elevated: false
                                    Accessible.role: Accessible.Grouping
                                    Accessible.name: qsTr("Replacement from %1 to %2")
                                                     .arg(String(root.field(replacementEntry.modelData, "heard", "")))
                                                     .arg(String(root.field(replacementEntry.modelData, "intended", "")))

                                    GridLayout {
                                        id: replacementRow
                                        anchors.fill: parent
                                        columns: width >= root.tokens.metric(500) ? 2 : 1
                                        columnSpacing: root.tokens.space12
                                        rowSpacing: root.tokens.space8

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: root.tokens.space4

                                            PlainText {
                                                Layout.fillWidth: true
                                                text: qsTr("Heard: %1")
                                                      .arg(String(root.field(replacementEntry.modelData, "heard", "")))
                                                color: root.tokens.mutedText
                                                font.family: root.tokens.fontFamily
                                                font.pixelSize: root.tokens.secondary
                                                wrapMode: Text.Wrap
                                            }

                                            PlainText {
                                                Layout.fillWidth: true
                                                text: qsTr("Use: %1")
                                                      .arg(String(root.field(replacementEntry.modelData, "intended", "")))
                                                color: root.tokens.text
                                                font.family: root.tokens.fontFamily
                                                font.pixelSize: root.tokens.body
                                                font.weight: Font.Medium
                                                wrapMode: Text.Wrap
                                            }
                                        }

                                        QuietButton {
                                            objectName: "removeReplacementButton_" + replacementEntry.entryId
                                            Layout.fillWidth: replacementRow.columns === 1
                                            tokens: root.tokens
                                            text: qsTr("Remove")
                                            kind: "danger"
                                            accessibleDescription: qsTr("Ask before removing this phrase replacement")
                                            onClicked: root.requestDestructiveAction(
                                                           "manual",
                                                           qsTr("%1 \u2192 %2")
                                                           .arg(String(root.field(replacementEntry.modelData, "heard", "")))
                                                           .arg(String(root.field(replacementEntry.modelData, "intended", ""))),
                                                           replacementEntry.entryId)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: root.tokens.space16

                        SectionHeading {
                            Layout.fillWidth: true
                            tokens: root.tokens
                            title: qsTr("Learned words")
                            description: qsTr("Review recurring uncommon terms learned from local dictation.")
                        }

                        InlineNotice {
                            Layout.fillWidth: true
                            tokens: root.tokens
                            kind: "info"
                            title: qsTr("You stay in control")
                            message: qsTr("Approve moves a useful term into Manual words. Forget removes only its local learning entry.")
                            detail: qsTr("Counts and recency describe local observations; they are not accuracy scores.")
                        }

                        InlineNotice {
                            objectName: "learnedWordsEmptyState"
                            Layout.fillWidth: true
                            visible: root.learnedWordCount === 0
                            tokens: root.tokens
                            kind: "info"
                            title: qsTr("No learned words yet")
                            message: qsTr("When local learning is on, recurring uncommon terms can appear here for your review.")
                        }

                        ColumnLayout {
                            objectName: "learnedWordsList"
                            Layout.fillWidth: true
                            spacing: root.tokens.space8
                            Accessible.role: Accessible.Grouping
                            Accessible.name: qsTr("Learned word entries")

                            Repeater {
                                model: root.learnedWords || []

                                delegate: GlassSurface {
                                    id: learnedEntry
                                    required property var modelData
                                    readonly property string entryId: root.rowId(learnedEntry.modelData)
                                    objectName: "learnedWordRow_" + entryId
                                    Layout.fillWidth: true
                                    implicitHeight: learnedRow.implicitHeight + padding * 2
                                    tokens: root.tokens
                                    role: "notice"
                                    padding: root.tokens.space12
                                    elevated: false
                                    Accessible.role: Accessible.Grouping
                                    Accessible.name: qsTr("Learned word: %1. %2")
                                                     .arg(root.wordText(learnedEntry.modelData))
                                                     .arg(root.learnedDetail(learnedEntry.modelData))

                                    GridLayout {
                                        id: learnedRow
                                        anchors.fill: parent
                                        columns: width >= root.tokens.metric(560) ? 2 : 1
                                        columnSpacing: root.tokens.space16
                                        rowSpacing: root.tokens.space8

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: root.tokens.space4

                                            PlainText {
                                                Layout.fillWidth: true
                                                text: root.wordText(learnedEntry.modelData)
                                                color: root.tokens.text
                                                font.family: root.tokens.fontFamily
                                                font.pixelSize: root.tokens.body
                                                font.weight: Font.Medium
                                                wrapMode: Text.Wrap
                                                Accessible.ignored: true
                                            }

                                            PlainText {
                                                Layout.fillWidth: true
                                                text: root.learnedDetail(learnedEntry.modelData)
                                                color: root.tokens.mutedText
                                                font.family: root.tokens.fontFamily
                                                font.pixelSize: root.tokens.secondary
                                                wrapMode: Text.Wrap
                                                Accessible.ignored: true
                                            }
                                        }

                                        Flow {
                                            Layout.fillWidth: true
                                            spacing: root.tokens.space8

                                            QuietButton {
                                                objectName: "approveLearnedButton_" + learnedEntry.entryId
                                                tokens: root.tokens
                                                text: qsTr("Approve")
                                                kind: "primary"
                                                enabled: !Boolean(root.field(learnedEntry.modelData, "approved", false))
                                                accessibleDescription: qsTr("Move %1 into Manual words")
                                                                       .arg(root.wordText(learnedEntry.modelData))
                                                onClicked: root.uiBridge.approveLearnedWord(
                                                               root.wordText(learnedEntry.modelData))
                                            }

                                            QuietButton {
                                                objectName: "forgetLearnedButton_" + learnedEntry.entryId
                                                tokens: root.tokens
                                                text: qsTr("Forget")
                                                kind: "danger"
                                                accessibleDescription: qsTr("Ask before removing %1 from local learning")
                                                                       .arg(root.wordText(learnedEntry.modelData))
                                                onClicked: root.requestDestructiveAction(
                                                               "learned",
                                                               root.wordText(learnedEntry.modelData),
                                                               learnedEntry.entryId)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            GlassSurface {
                objectName: "vocabularyLocalFileSurface"
                x: root.pageMargin
                width: Math.max(0, parent.width - root.pageMargin * 2)
                implicitHeight: localFileContent.implicitHeight + padding * 2
                tokens: root.tokens
                role: "notice"
                padding: root.tokens.space16
                elevated: false

                GridLayout {
                    id: localFileContent
                    anchors.fill: parent
                    columns: width >= root.tokens.metric(560) ? 2 : 1
                    columnSpacing: root.tokens.space16
                    rowSpacing: root.tokens.space12

                    SectionHeading {
                        Layout.fillWidth: true
                        tokens: root.tokens
                        title: qsTr("Local file controls")
                        description: qsTr("Expert option: inspect or edit dictionary.txt directly. Comments, blank lines, ordering, and unknown lines are preserved by Speakr edits.")
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: root.tokens.space8

                        QuietButton {
                            objectName: "openDictionaryFileButton"
                            tokens: root.tokens
                            text: qsTr("Open dictionary file")
                            accessibleDescription: qsTr("Open the local plain-text vocabulary file")
                            onClicked: root.uiBridge.openLocal("dictionary")
                        }

                        QuietButton {
                            id: reloadButton
                            objectName: "reloadVocabularyButton"
                            tokens: root.tokens
                            text: qsTr("Reload from file")
                            kind: "secondary"
                            accessibleDescription: qsTr("Reload Vocabulary after editing the local file")
                            onClicked: root.reloadVocabulary()
                        }
                    }
                }
            }

            Item {
                width: parent.width
                height: root.tokens.space24
            }
        }
    }

    Dialog {
        id: confirmDialog
        objectName: "vocabularyConfirmation"
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(root.width - root.tokens.space32,
                        root.tokens.metric(520))
        x: Math.max(root.tokens.space16, (root.width - width) / 2)
        y: Math.max(root.tokens.space16, (root.height - height) / 2)
        padding: root.tokens.space24
        onOpened: cancelRemoval.forceActiveFocus(Qt.TabFocusReason)
        onClosed: {
            root.pendingAction = ""
            root.pendingTarget = ""
            root.pendingId = ""
        }

        background: GlassSurface {
            tokens: root.tokens
            role: "major"
            padding: 0
        }

        contentItem: ColumnLayout {
            spacing: root.tokens.space16
            Accessible.role: Accessible.Dialog
            Accessible.name: root.pendingAction === "learned"
                             ? qsTr("Confirm forget learned word")
                             : qsTr("Confirm remove vocabulary entry")
            Accessible.description: root.pendingTarget

            SectionHeading {
                Layout.fillWidth: true
                tokens: root.tokens
                title: root.pendingAction === "learned"
                       ? qsTr("Forget this learned word?")
                       : qsTr("Remove this vocabulary entry?")
                description: root.pendingAction === "learned"
                             ? qsTr("Speakr will remove only its local learning entry.")
                             : qsTr("Speakr will remove the content-bound entry from the local dictionary file.")
            }

            PlainText {
                Layout.fillWidth: true
                text: root.pendingTarget
                color: root.tokens.text
                font.family: root.tokens.fontFamily
                font.pixelSize: root.tokens.body
                font.weight: Font.Medium
                wrapMode: Text.Wrap
                Accessible.name: text
            }

            Flow {
                Layout.fillWidth: true
                spacing: root.tokens.space8

                QuietButton {
                    id: cancelRemoval
                    objectName: "cancelVocabularyDeletion"
                    tokens: root.tokens
                    text: qsTr("Cancel")
                    kind: "primary"
                    accessibleDescription: qsTr("Keep this vocabulary entry")
                    onClicked: confirmDialog.close()
                }

                QuietButton {
                    objectName: "confirmVocabularyDeletion"
                    tokens: root.tokens
                    text: root.pendingAction === "learned"
                          ? qsTr("Forget") : qsTr("Remove")
                    kind: "danger"
                    accessibleDescription: root.pendingAction === "learned"
                                           ? qsTr("Forget the named learned word")
                                           : qsTr("Remove the named vocabulary entry")
                    onClicked: root.confirmDestructiveAction()
                }
            }
        }
    }
}
