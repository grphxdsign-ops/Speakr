#!/usr/bin/env bash
# Speakr launcher (macOS) — creates the venv on first run, then starts in the
# background. Look for the mic icon in the menu bar.
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
    echo "First run: setting up Python environment..."
    rm -rf .venv  # clear a Windows-copied venv if present
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi
nohup .venv/bin/python -m speakr >/dev/null 2>&1 &
echo "Speakr started — look for the mic icon in the menu bar."
echo "First time? Grant Microphone, Input Monitoring and Accessibility"
echo "permissions when macOS asks (System Settings -> Privacy & Security)."
