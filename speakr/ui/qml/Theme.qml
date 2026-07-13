import QtQuick

QtObject {
    id: theme

    // Public preferences. Keep these independent from native-window state so
    // the same theme can be used by the main window, HUD, and test harnesses.
    property string mode: "system"
    property string density: "comfortable"
    property real textScale: 1.0
    property bool reduceMotion: false
    property bool systemHighContrast: false
    property string visualEffects: "system" // system | full | reduced | off
    property bool systemReduceTransparency: false
    property bool softwareRenderer: false

    property SystemPalette systemPalette: SystemPalette {
        colorGroup: SystemPalette.Active
    }

    readonly property bool highContrast: mode === "high_contrast"
                                         || (mode === "system" && systemHighContrast)
    readonly property bool systemDark: luminance(systemPalette.window) < 0.48
    readonly property bool dark: mode === "dark" || (mode === "system" && systemDark)
    readonly property string effectTier: {
        if (highContrast || visualEffects === "off")
            return "off"
        if (systemReduceTransparency || softwareRenderer
                || visualEffects === "reduced")
            return "reduced"
        return "full"
    }

    // Luminous Orbit source palette. High Contrast always delegates to the
    // operating system and removes branded atmosphere and transparency.
    readonly property color canvas: highContrast ? systemPalette.window
                                                 : (dark ? "#090B18" : "#EDF1FA")
    readonly property color surfaceStrong: highContrast ? systemPalette.base
                                                        : (dark ? "#20243A" : "#F8FAFF")
    readonly property color textPrimary: highContrast ? systemPalette.windowText
                                                      : (dark ? "#F2F3FC" : "#17182A")
    readonly property color textSecondary: highContrast ? systemPalette.text
                                                        : (dark ? "#B4B7C9" : "#55596D")
    readonly property color borderMeaningful: highContrast ? systemPalette.windowText
                                                           : (dark ? "#737A99" : "#747A92")
    readonly property color accent: highContrast ? systemPalette.highlight
                                                 : (dark ? "#A89AFB" : "#6657D8")
    readonly property color accentText: highContrast ? systemPalette.highlightedText
                                                     : (dark ? "#17182A" : "#F8FAFF")
    readonly property color accentHoverSurface: highContrast ? systemPalette.highlight
                                                             : (dark ? "#B5A9FF" : "#594AC7")
    readonly property color accentPressedSurface: highContrast ? systemPalette.highlight
                                                               : (dark ? "#9788E3" : "#4F41B3")

    // Compatibility aliases used throughout the existing pages. These stay
    // opaque; transparent material is opt-in through the role tokens below.
    readonly property color background: canvas
    readonly property color surface: surfaceStrong
    readonly property color surfaceRaised: highContrast ? systemPalette.button
                                                        : (dark ? "#2A2F49" : "#E6EAF5")
    readonly property color text: textPrimary
    readonly property color mutedText: textSecondary
    readonly property color border: borderMeaningful

    readonly property color success: highContrast ? systemPalette.highlight
                                                  : (dark ? "#83D8AA" : "#176D3B")
    readonly property color successSurface: highContrast ? systemPalette.base
                                                         : (dark ? "#17352A" : "#E4F4EA")
    readonly property color warning: highContrast ? systemPalette.windowText
                                                  : (dark ? "#F2CD7D" : "#795600")
    readonly property color warningSurface: highContrast ? systemPalette.base
                                                         : (dark ? "#3A301D" : "#FFF1C9")
    readonly property color danger: highContrast ? systemPalette.windowText
                                                 : (dark ? "#FFAAAA" : "#A52A2A")
    readonly property color dangerSurface: highContrast ? systemPalette.base
                                                        : (dark ? "#3D222E" : "#FDE9E9")
    readonly property color dangerHoverSurface: highContrast ? systemPalette.highlight
                                                             : danger
    readonly property color dangerPressedSurface: highContrast ? systemPalette.highlight
                                                               : (dark ? "#E7929E" : "#872020")
    readonly property color dangerStrongText: highContrast ? systemPalette.highlightedText
                                                           : accentText
    readonly property color info: highContrast ? systemPalette.highlight
                                               : (dark ? "#8FC9F5" : "#245F93")
    readonly property color infoSurface: highContrast ? systemPalette.base
                                                      : (dark ? "#173149" : "#E2F1FC")
    readonly property color focus: highContrast ? systemPalette.highlight : accent
    readonly property color disabledText: withAlpha(text, 0.52)
    readonly property color hover: highContrast ? systemPalette.highlight
                                                : withAlpha(accent, dark ? 0.20 : 0.12)
    readonly property color pressed: highContrast ? systemPalette.highlight
                                                  : withAlpha(accent, dark ? 0.30 : 0.20)

    // Local, static atmosphere. All fields stay below the 18% contract and
    // disappear when effects are off or High Contrast is active.
    readonly property color atmosphereVioletBase: dark ? "#8F7CFF" : "#7665E8"
    readonly property color atmosphereCyanBase: dark ? "#62D4F2" : "#4AA8CE"
    readonly property color atmosphereBlushBase: dark ? "#F49AC2" : "#CF779F"
    readonly property color orbitLineBase: dark ? "#D6D0FF" : "#5D568D"
    readonly property color shadowBase: dark ? "#02030A" : "#39335F"
    readonly property color atmosphereViolet: effectTier === "off"
                                              ? "transparent"
                                              : withAlpha(atmosphereVioletBase,
                                                          effectTier === "reduced" ? 0.06 : 0.16)
    readonly property color atmosphereCyan: effectTier === "off"
                                            ? "transparent"
                                            : withAlpha(atmosphereCyanBase,
                                                        effectTier === "reduced" ? 0.04 : 0.12)
    readonly property color atmosphereBlush: effectTier === "off"
                                             ? "transparent"
                                             : withAlpha(atmosphereBlushBase,
                                                         effectTier === "reduced" ? 0.035 : 0.10)
    readonly property color orbitLine: effectTier === "off"
                                       ? "transparent"
                                       : withAlpha(orbitLineBase,
                                                   effectTier === "reduced" ? 0.08 : 0.16)

    readonly property real shellOpacity: materialOpacity("shell")
    readonly property real navigationOpacity: materialOpacity("navigation")
    readonly property real majorOpacity: materialOpacity("major")
    readonly property real noticeOpacity: materialOpacity("notice")
    readonly property real contentOpacity: materialOpacity("content")
    readonly property real hudOpacity: materialOpacity("hud")
    readonly property color shellSurface: materialColor("shell")
    readonly property color navigationSurface: materialColor("navigation")
    readonly property color majorSurface: materialColor("major")
    readonly property color noticeSurface: materialColor("notice")
    readonly property color contentSurface: materialColor("content")
    readonly property color hudSurface: materialColor("hud")
    readonly property color shadow: highContrast || effectTier === "off"
                                    ? "transparent"
                                    : withAlpha(shadowBase,
                                                effectTier === "reduced" ? 0.12 : 0.20)

    readonly property string fontFamily: Qt.platform.os === "windows"
                                         ? "Segoe UI"
                                         : (Qt.platform.os === "osx" ? "SF Pro Text" : "")
    readonly property int pageHeading: fontSize(28)
    readonly property int sectionHeading: fontSize(22)
    readonly property int statusHeading: fontSize(18)
    readonly property int body: fontSize(16)
    readonly property int secondary: fontSize(15)
    readonly property int label: fontSize(16)

    readonly property int space4: metric(4)
    readonly property int space8: metric(8)
    readonly property int space12: metric(12)
    readonly property int space16: metric(16)
    readonly property int space24: metric(24)
    readonly property int space32: metric(32)

    readonly property int radiusSmall: metric(10)
    readonly property int radiusControl: metric(14)
    readonly property int radiusPanel: metric(20)
    readonly property int radiusShell: metric(28)
    readonly property int radius: radiusControl
    readonly property int radiusLarge: radiusPanel
    readonly property int focusWidth: 2
    readonly property int focusClearance: metric(2)
    readonly property int borderWidth: highContrast ? 2 : 1
    readonly property int controlHeight: Math.max(
                                             44,
                                             Math.round((density === "compact" ? 44 : 48)
                                                        * Math.min(textScale, 1.5)))
    readonly property int rowHeight: Math.max(controlHeight, metric(density === "compact" ? 52 : 60))

    readonly property int motionFast: reduceMotion ? 0 : 100
    readonly property int motionStandard: reduceMotion ? 0 : 160
    readonly property int motionEmphasis: reduceMotion ? 0 : 220
    readonly property int motionHover: motionFast
    readonly property int motionToggle: reduceMotion ? 0 : 140
    readonly property int motionDisclosure: reduceMotion ? 0 : 120
    readonly property int motionStage: motionStandard
    readonly property int motionOnboarding: reduceMotion ? 0 : 180

    function fontSize(value) {
        return Math.max(1, Math.round(value * textScale))
    }

    function metric(value) {
        // Text may scale to 200%, but multiplying every margin and control by
        // two leaves no useful viewport. A modest metric cap preserves large
        // labels while layouts reflow vertically.
        return Math.max(1, Math.round(value * Math.max(1.0, Math.min(1.25, textScale))))
    }

    function luminance(colorValue) {
        return 0.2126 * colorValue.r + 0.7152 * colorValue.g + 0.0722 * colorValue.b
    }

    function withAlpha(colorValue, alphaValue) {
        return Qt.rgba(colorValue.r, colorValue.g, colorValue.b, alphaValue)
    }

    function materialOpacity(role) {
        if (highContrast || effectTier === "off")
            return 1.0
        if (effectTier === "reduced")
            return role === "shell" ? 0.94
                 : role === "navigation" ? 0.96
                 : role === "major" ? 0.96
                 : role === "notice" ? 0.96 : 1.0
        if (role === "shell") return dark ? 0.72 : 0.78
        if (role === "navigation") return dark ? 0.76 : 0.82
        if (role === "major") return dark ? 0.84 : 0.88
        if (role === "notice") return dark ? 0.88 : 0.92
        if (role === "content") return dark ? 0.94 : 0.96
        return 1.0 // The HUD is always local and effectively opaque.
    }

    function materialColor(role) {
        var base = highContrast ? systemPalette.base : surfaceStrong
        return withAlpha(base, materialOpacity(role))
    }
}
