#!/usr/bin/env bash
# Build a self-contained Speakr.app on macOS from an already-prepared
# Python 3.11 release environment. The installed app never runs pip.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
APP="dist/Speakr.app"

"$PYTHON" - <<'PY'
import sys
if sys.version_info[:2] != (3, 11):
    raise SystemExit(
        f"package_mac.sh requires Python 3.11, found {sys.version_info.major}.{sys.version_info.minor}"
    )
try:
    import PyInstaller  # noqa: F401
except ImportError as exc:
    raise SystemExit("PyInstaller must be installed in the selected build environment") from exc
PY
"$PYTHON" scripts/check_qt_build_environment.py

rm -rf "$APP"

ICON_ARGS=()
if [ -f assets/icon.png ] && command -v iconutil >/dev/null; then
    ICON_ROOT="$(mktemp -d)"
    ICONSET="$ICON_ROOT/speakr.iconset"
    mkdir -p "$ICONSET"
    for s in 16 32 128 256 512; do
        sips -z "$s" "$s" assets/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
        sips -z "$((s * 2))" "$((s * 2))" assets/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$ICON_ROOT/Speakr.icns"
    ICON_ARGS=(--icon "$ICON_ROOT/Speakr.icns")
fi

"$PYTHON" -m PyInstaller --noconfirm --windowed \
    --name Speakr \
    --osx-bundle-identifier com.speakr.dictation \
    "${ICON_ARGS[@]}" \
    --paths . \
    --collect-all ctranslate2 \
    --collect-all faster_whisper \
    --collect-all onnxruntime \
    --hidden-import pystray._darwin \
    --hidden-import PySide6.QtQuick \
    --hidden-import PySide6.QtQuickControls2 \
    --add-data "speakr/ui/qml:speakr/ui/qml" \
    --add-data "assets/icon.png:assets" \
    --exclude-module PySide6.QtWebEngine \
    --exclude-module PySide6.QtWebEngineCore \
    --exclude-module PySide6.QtWebEngineQuick \
    --exclude-module PySide6.QtWebEngineWidgets \
    --exclude-module PySide6.QtWebView \
    --exclude-module PySide6.QtWebChannel \
    scripts/frozen_entry.py

cat > "$APP/Contents/Resources/THIRD_PARTY_NOTICES.txt" <<'NOTICE'
Speakr includes Qt for Python / PySide6-Essentials 6.11.1.
Qt for Python is copyright The Qt Company Ltd. and contributors.
The installed open-source package is offered under LGPL-3.0-only,
GPL-2.0-only, or GPL-3.0-only, as described by its package metadata.
Speakr does not modify Qt source files.
NOTICE

PLIST="$APP/Contents/Info.plist"
plutil -replace LSUIElement -bool true "$PLIST" 2>/dev/null \
    || plutil -insert LSUIElement -bool true "$PLIST"
plutil -replace NSMicrophoneUsageDescription \
    -string "Speakr transcribes your dictation locally on this Mac. Audio never leaves the machine." \
    "$PLIST" 2>/dev/null \
    || plutil -insert NSMicrophoneUsageDescription \
        -string "Speakr transcribes your dictation locally on this Mac. Audio never leaves the machine." \
        "$PLIST"

"$PYTHON" scripts/scan_artifact_privacy.py "$APP"

# PyInstaller performs an ad-hoc sign, but Info.plist changed afterward.
# Re-sign the final local bundle so Apple Silicon can launch it. Official
# Developer ID signing and notarization remain in the release workflow.
if command -v codesign >/dev/null; then
    xattr -cr "$APP"
    codesign --force --deep --sign - "$APP"
    codesign --verify --deep --strict "$APP"
fi

echo "Built self-contained $APP"
echo "Install: mv $APP /Applications/"
echo "The installed app makes no package-manager or update-check requests."
echo "Its only non-loopback runtime download is the first-run speech model."
