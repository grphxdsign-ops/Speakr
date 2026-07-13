"""PyInstaller entry point for the packaged Speakr builds (both platforms).

speakr.config derives its data root (config.json, dictionary, log) from the
package location when SPEAKR_HOME is unset. In a frozen build the package
lives inside the bundle (or a per-launch temp dir), so user data would end
up somewhere wrong — or be silently reset. Pin SPEAKR_HOME to the platform's
standard per-user data directory BEFORE importing speakr (config reads the
env at import time):

  macOS    ~/Library/Application Support/Speakr
  Windows  %APPDATA%\\Speakr
"""

import os
import sys

if getattr(sys, "frozen", False) and not os.environ.get("SPEAKR_HOME"):
    if sys.platform == "darwin":
        home = os.path.expanduser("~/Library/Application Support/Speakr")
    else:
        home = os.path.join(
            os.environ.get("APPDATA") or os.path.expanduser("~"), "Speakr"
        )
    os.makedirs(home, exist_ok=True)
    os.environ["SPEAKR_HOME"] = home

# The exact-artifact core proof installs its loopback-only socket policy and
# offline model environment before importing any Speakr application module.
# In ordinary launches the environment variable is absent and this is inert.
from speakr.release_core_proof import install_core_proof_from_environment

install_core_proof_from_environment()

from speakr.app import main

main()
