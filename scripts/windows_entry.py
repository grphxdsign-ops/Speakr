"""PyInstaller entry point for the Windows Speakr.exe build.

A --onefile exe unpacks itself into a fresh temp directory on every launch,
and speakr.config derives its data root (config.json, dictionary, log) from
the package location when SPEAKR_HOME is unset — which would silently reset
the user's config on every run. So for frozen builds, pin SPEAKR_HOME to
%APPDATA%\\Speakr BEFORE importing speakr (config reads the env at import
time), mirroring what the Mac .app launcher does with Application Support.
"""

import os
import sys

if getattr(sys, "frozen", False) and not os.environ.get("SPEAKR_HOME"):
    home = os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), "Speakr"
    )
    os.makedirs(home, exist_ok=True)
    os.environ["SPEAKR_HOME"] = home

from speakr.app import main

main()
