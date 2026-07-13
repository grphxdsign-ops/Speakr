import QtQuick

QtObject {
    id: theme

    property string mode: "system"
    property string density: "comfortable"
    property real textScale: 1.0
    property bool reduceMotion: false
    property bool systemHighContrast: false

    property SystemPalette systemPalette: SystemPalette {
        colorGroup: SystemPalette.Active
    }

    readonly property bool highContrast: mode === "high_contrast"
                                         || (mode === "system" && systemHighContrast)
    readonly property bool systemDark: luminance(systemPalette.window) < 0.48
    readonly property bool dark: mode === "dark" || (mode === "system" && systemDark)

    // OKLCH source tokens from DESIGN.md, converted to sRGB for Qt Quick.
    readonly property color background: highContrast ? systemPalette.window
                                                     : (dark ? "#0d1219" : "#f1f6fc")
    readonly property color surface: highContrast ? systemPalette.base
                                                  : (dark ? "#171d25" : "#f9fcff")
    readonly property color surfaceRaised: highContrast ? systemPalette.button
                                                        : (dark ? "#202833" : "#edf3fa")
    readonly property color text: highContrast ? systemPalette.windowText
                                               : (dark ? "#e3e8ef" : "#17202b")
    readonly property color mutedText: highContrast ? systemPalette.text
                                                    : (dark ? "#9da5b0" : "#4b535e")
    readonly property color border: highContrast ? systemPalette.windowText
                                                 : (dark ? "#697584" : "#7a8594")
    readonly property color accent: highContrast ? systemPalette.highlight
                                                 : (dark ? "#6aa7f4" : "#026fd7")
    readonly property color accentText: highContrast ? systemPalette.highlightedText
                                                     : (dark ? "#101722" : "#f8fbff")
    readonly property color success: highContrast ? systemPalette.highlight
                                                  : (dark ? "#73d39b" : "#176d3b")
    readonly property color successSurface: highContrast ? systemPalette.base
                                                         : (dark ? "#193328" : "#e4f4ea")
    readonly property color warning: highContrast ? systemPalette.windowText
                                                  : (dark ? "#f0c46c" : "#795600")
    readonly property color warningSurface: highContrast ? systemPalette.base
                                                         : (dark ? "#392f1a" : "#fff1c9")
    readonly property color danger: highContrast ? systemPalette.windowText
                                                 : (dark ? "#ff9e9e" : "#a52a2a")
    readonly property color dangerSurface: highContrast ? systemPalette.base
                                                        : (dark ? "#3b2024" : "#fde9e9")
    readonly property color focus: accent
    readonly property color disabledText: withAlpha(text, 0.48)
    readonly property color hover: withAlpha(accent, dark ? 0.18 : 0.10)
    readonly property color pressed: withAlpha(accent, dark ? 0.26 : 0.17)

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
    readonly property int radiusSmall: metric(6)
    readonly property int radius: metric(10)
    readonly property int radiusLarge: metric(14)
    readonly property int controlHeight: Math.max(
                                             44,
                                             Math.round((density === "compact" ? 44 : 48)
                                                        * Math.min(textScale, 1.5)))
    readonly property int rowHeight: Math.max(controlHeight, metric(density === "compact" ? 52 : 60))

    readonly property int motionFast: reduceMotion ? 0 : 100
    readonly property int motionStandard: reduceMotion ? 0 : 160
    readonly property int motionEmphasis: reduceMotion ? 0 : 220

    function fontSize(value) {
        return Math.max(1, Math.round(value * textScale))
    }

    function metric(value) {
        // Text may scale to 200%, but multiplying every margin and control by
        // two leaves no useful viewport.  A modest metric cap preserves large
        // labels while layouts reflow vertically.
        return Math.max(1, Math.round(value * Math.max(1.0, Math.min(1.25, textScale))))
    }

    function luminance(colorValue) {
        return 0.2126 * colorValue.r + 0.7152 * colorValue.g + 0.0722 * colorValue.b
    }

    function withAlpha(colorValue, alphaValue) {
        return Qt.rgba(colorValue.r, colorValue.g, colorValue.b, alphaValue)
    }
}
