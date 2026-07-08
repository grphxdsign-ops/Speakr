#!/usr/bin/env bash
# Speakr launcher (macOS) — creates the venv on first run, then starts in the
# background. Look for the mic icon in the menu bar.
cd "$(dirname "$0")"

# Apple Silicon Macs' /usr/bin/python3 (Xcode Command Line Tools) is a
# universal binary — which slice runs depends on how the PARENT process was
# launched (e.g. Terminal set to "Open using Rosetta"), not the hardware.
# sysctl reports true hardware capability regardless of Rosetta translation
# already in effect, so pin to it explicitly — otherwise a venv built under
# one architecture crashes on import (mismatched .so files) if this script
# is ever run again from a differently-configured terminal.
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    PY=(arch -arm64 python3)
else
    PY=(python3)
fi

if [ -x ".venv/bin/python" ]; then
    have_arch="$(.venv/bin/python -c 'import platform;print(platform.machine())' 2>/dev/null)"
    want_arch="$("${PY[@]}" -c 'import platform;print(platform.machine())' 2>/dev/null)"
    [ -n "$want_arch" ] && [ "$have_arch" != "$want_arch" ] && rm -rf .venv
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "First run: setting up Python environment..."
    rm -rf .venv  # clear a Windows-copied venv if present
    "${PY[@]}" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi
nohup .venv/bin/python -m speakr >/dev/null 2>&1 &
echo "Speakr started — look for the mic icon in the menu bar."
echo "First time? Grant Microphone, Input Monitoring and Accessibility"
echo "permissions when macOS asks (System Settings -> Privacy & Security)."
