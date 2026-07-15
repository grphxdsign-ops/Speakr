#!/usr/bin/env bash
# Build and sign a self-contained Speakr.app from a prepared Python 3.11
# release environment. CI and local release proofs use this same entry point.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
APP="$ROOT/dist/Speakr.app"
MAIN_EXECUTABLE="$APP/Contents/MacOS/Speakr"
SIGN_IDENTITY="${SPEAKR_SIGN_IDENTITY:--}"
ICON_ROOT=""

cleanup() {
    if [ -n "$ICON_ROOT" ] && [ -d "$ICON_ROOT" ]; then
        rm -rf -- "$ICON_ROOT"
    fi
}
trap cleanup EXIT

"$PYTHON" - <<'PY'
import importlib.metadata as metadata
import sys

if sys.version_info[:2] != (3, 11):
    raise SystemExit(
        f"package_mac.sh requires Python 3.11, found {sys.version_info.major}.{sys.version_info.minor}"
    )
if metadata.version("PyInstaller") != "6.21.0":
    raise SystemExit("package_mac.sh requires the PyInstaller version pinned in requirements-release.txt")
PY
"$PYTHON" scripts/check_qt_build_environment.py
"$PYTHON" -m pip check

# The only recursive removal is the fixed app output below this repository.
case "$APP" in
    "$ROOT/dist/Speakr.app") rm -rf -- "$APP" ;;
    *) echo "Refusing to remove unexpected app path: $APP" >&2; exit 1 ;;
esac

ICON_ARGS=()
if [ -f assets/icon.png ] && command -v iconutil >/dev/null; then
    ICON_ROOT="$(mktemp -d)"
    ICONSET="$ICON_ROOT/speakr.iconset"
    mkdir -p "$ICONSET"
    for size in 16 32 128 256 512; do
        sips -z "$size" "$size" assets/icon.png \
            --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
        sips -z "$((size * 2))" "$((size * 2))" assets/icon.png \
            --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$ICON_ROOT/Speakr.icns"
    ICON_ARGS=(--icon "$ICON_ROOT/Speakr.icns")
fi

"$PYTHON" scripts/build_release.py "${ICON_ARGS[@]}"

cat > "$APP/Contents/Resources/THIRD_PARTY_NOTICES.txt" <<'NOTICE'
Speakr includes Qt for Python / PySide6-Essentials 6.11.1.
Qt for Python is copyright The Qt Company Ltd. and contributors.
The installed open-source package is offered under LGPL-3.0-only,
GPL-2.0-only, or GPL-3.0-only, as described by its package metadata.
Speakr does not modify Qt source files.
NOTICE

PLIST="$APP/Contents/Info.plist"
# Regular app presence: Dock icon and Cmd-Tab entry (the menu-bar tray icon
# is additional, not a replacement — user decision 2026-07-15).
plutil -replace LSUIElement -bool false "$PLIST" 2>/dev/null \
    || plutil -insert LSUIElement -bool false "$PLIST"
plutil -replace NSMicrophoneUsageDescription \
    -string "Speakr transcribes your dictation locally on this Mac. Audio never leaves the machine." \
    "$PLIST" 2>/dev/null \
    || plutil -insert NSMicrophoneUsageDescription \
        -string "Speakr transcribes your dictation locally on this Mac. Audio never leaves the machine." \
        "$PLIST"

# Scan the complete, final-content bundle before any signature can obscure
# where a packaging failure originated.
"$PYTHON" scripts/scan_artifact_privacy.py "$APP"

if ! command -v codesign >/dev/null; then
    echo "codesign is required to produce a launchable macOS app" >&2
    exit 1
fi

xattr -cr "$APP"

SIGN_ARGS=(--force --sign "$SIGN_IDENTITY")
if [ "$SIGN_IDENTITY" != "-" ]; then
    SIGN_ARGS+=(--options runtime --timestamp)
fi

# Sign inner Mach-O files and code bundles from deepest to shallowest, then
# seal the main app last. This is the explicit nested-code order Apple expects;
# do not replace it with codesign's deprecated recursive signing shortcut.
while IFS= read -r -d '' item; do
    if [ "$item" = "$MAIN_EXECUTABLE" ]; then
        continue
    fi
    if [ -d "$item" ]; then
        case "$item" in
            *.framework|*.app|*.xpc|*.bundle) codesign "${SIGN_ARGS[@]}" "$item" ;;
        esac
    elif file -b "$item" | grep -q 'Mach-O'; then
        codesign "${SIGN_ARGS[@]}" "$item"
    fi
done < <(find "$APP/Contents" -depth \( -type f -o -type d \) -print0)

codesign "${SIGN_ARGS[@]}" \
    --entitlements "$ROOT/scripts/entitlements.plist" \
    "$APP"

# Verify every signed unit independently so a bad nested signature cannot be
# masked by checking only the outer bundle.
while IFS= read -r -d '' item; do
    if [ -d "$item" ]; then
        case "$item" in
            *.framework|*.app|*.xpc|*.bundle) codesign --verify --strict --verbose=2 "$item" ;;
        esac
    elif file -b "$item" | grep -q 'Mach-O'; then
        codesign --verify --strict --verbose=2 "$item"
    fi
done < <(find "$APP/Contents" -depth \( -type f -o -type d \) -print0)
codesign --verify --strict --verbose=2 "$APP"

if [ "$SIGN_IDENTITY" = "-" ]; then
    echo "Built ad-hoc signed local proof: $APP"
else
    echo "Built Developer ID signed app: $APP"
fi
echo "The installed app performs no package-manager or update-check requests."
echo "Its only non-loopback runtime download is the first-run speech model."
