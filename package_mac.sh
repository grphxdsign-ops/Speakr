#!/usr/bin/env bash
# Build Speakr.app — run ON the Mac from the repo root:  bash package_mac.sh
# Produces dist/Speakr.app. Move it to /Applications and open it like any app.
set -e
cd "$(dirname "$0")"

APP="dist/Speakr.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Bundle the code (user data does NOT live in the bundle — see SPEAKR_HOME)
cp -R speakr "$APP/Contents/Resources/speakr"
cp requirements.txt "$APP/Contents/Resources/"

# Icon: png -> icns
if [ -f assets/icon.png ] && command -v iconutil >/dev/null; then
    ICONSET="$(mktemp -d)/speakr.iconset"
    mkdir -p "$ICONSET"
    for s in 16 32 128 256 512; do
        sips -z $s $s assets/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
        sips -z $((s * 2)) $((s * 2)) assets/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Speakr.icns" || true
fi

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleName</key><string>Speakr</string>
    <key>CFBundleDisplayName</key><string>Speakr</string>
    <key>CFBundleIdentifier</key><string>com.speakr.dictation</string>
    <key>CFBundleVersion</key><string>0.1.0</string>
    <key>CFBundleShortVersionString</key><string>0.1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>Speakr</string>
    <key>CFBundleIconFile</key><string>Speakr</string>
    <key>LSUIElement</key><true/>
    <key>NSMicrophoneUsageDescription</key><string>Speakr transcribes your dictation locally on this Mac. Audio never leaves the machine.</string>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/Speakr" <<'LAUNCH'
#!/usr/bin/env bash
# Speakr.app launcher. Code ships inside the bundle (Resources); the Python
# environment and all user data live in ~/Library/Application Support/Speakr.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
SUP="$HOME/Library/Application Support/Speakr"
mkdir -p "$SUP"
export SPEAKR_HOME="$SUP"
export PYTHONPATH="$RES"
VENV="$SUP/venv"

# Apple Silicon Macs' /usr/bin/python3 (from Xcode Command Line Tools) is a
# universal binary — which slice actually executes depends on how the
# PARENT process was launched (e.g. Terminal set to "Open using Rosetta"),
# not the hardware. `sysctl hw.optional.arm64` reports the true hardware
# capability regardless of any Rosetta translation already in effect on
# this process, so pin the venv to it explicitly rather than leaving it to
# ambient shell state — otherwise a venv built in one architecture crashes
# on import when later launched in the other (mismatched .so files).
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    PY=(arch -arm64 python3)
else
    PY=(python3)
fi

# Self-heal a venv that was built for the wrong architecture (including
# ones created before this fix existed) instead of crashing on import.
if [ -x "$VENV/bin/python" ]; then
    have_arch="$("$VENV/bin/python" -c 'import platform;print(platform.machine())' 2>/dev/null)"
    want_arch="$("${PY[@]}" -c 'import platform;print(platform.machine())' 2>/dev/null)"
    if [ -n "$want_arch" ] && [ "$have_arch" != "$want_arch" ]; then
        rm -rf "$VENV"
    fi
fi

if [ ! -x "$VENV/bin/python" ]; then
    "${PY[@]}" -m venv "$VENV"
    "$VENV/bin/python" -m pip install --upgrade pip >> "$SUP/setup.log" 2>&1
    "$VENV/bin/python" -m pip install -r "$RES/requirements.txt" >> "$SUP/setup.log" 2>&1
fi
exec "$VENV/bin/python" -m speakr
LAUNCH
chmod +x "$APP/Contents/MacOS/Speakr"

echo "Built $APP"
echo "Install:  mv $APP /Applications/"
echo "First launch installs Python packages + downloads the model (a few"
echo "minutes, menu-bar icon appears when ready). Progress:"
echo "  ~/Library/Application Support/Speakr/setup.log and speakr.log"
