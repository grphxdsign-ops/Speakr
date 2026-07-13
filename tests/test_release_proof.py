from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from speakr.release_proof import (
    PROOF_PATH_ENV,
    PROOF_QUIT_ENV,
    proof_requested,
    quit_after_proof_requested,
    write_native_ready,
)


class ReleaseProofTests(unittest.TestCase):
    def test_no_environment_request_writes_nothing(self):
        with mock.patch.dict(
            os.environ,
            {PROOF_PATH_ENV: "", PROOF_QUIT_ENV: ""},
            clear=False,
        ):
            self.assertFalse(proof_requested())
            self.assertFalse(quit_after_proof_requested())
            self.assertFalse(
                write_native_ready(
                    tray_visible=True,
                    main_window_visible=True,
                    main_window_exposed=True,
                    main_window_required=True,
                    material="mica",
                    effect_tier="full",
                    native_material_available=True,
                    custom_chrome_enabled=True,
                    software_renderer=False,
                )
            )

    def test_receipt_is_atomic_sanitized_and_fixed_vocabulary(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "proof" / "native-ready.json"
            with mock.patch.dict(
                os.environ,
                {PROOF_PATH_ENV: str(destination), PROOF_QUIT_ENV: "yes"},
                clear=False,
            ):
                self.assertTrue(proof_requested())
                self.assertTrue(quit_after_proof_requested())
                self.assertTrue(
                    write_native_ready(
                        tray_visible=1,
                        main_window_visible=True,
                        main_window_exposed=True,
                        main_window_required=True,
                        material="mica",
                        effect_tier="full",
                        native_material_available=True,
                        custom_chrome_enabled=True,
                        software_renderer=False,
                    )
                )

            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(
                payload,
                {
                    "schema": 1,
                    "frontend": "native",
                    "tray_visible": True,
                    "main_window_visible": True,
                    "main_window_exposed": True,
                    "main_window_required": True,
                    "material": "mica",
                    "effect_tier": "full",
                    "native_material_available": True,
                    "chrome": "custom",
                    "renderer": "hardware",
                },
            )
            self.assertEqual(list(destination.parent.glob("*.tmp")), [])
            serialized = destination.read_text(encoding="utf-8").casefold()
            for forbidden in (
                "audio",
                "transcript",
                "clipboard",
                "selection",
                "window_title",
                "screen_content",
            ):
                self.assertNotIn(forbidden, serialized)

    def test_unknown_capabilities_fail_closed_to_solid_system_frame(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "native-ready.json"
            with mock.patch.dict(
                os.environ,
                {PROOF_PATH_ENV: str(destination)},
                clear=False,
            ):
                self.assertTrue(
                    write_native_ready(
                        tray_visible=False,
                        main_window_visible=False,
                        main_window_exposed=False,
                        main_window_required=False,
                        material="remote_glass",
                        effect_tier="ultra",
                        native_material_available=False,
                        custom_chrome_enabled=False,
                        software_renderer=True,
                    )
                )
            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(payload["material"], "solid")
            self.assertEqual(payload["effect_tier"], "off")
            self.assertEqual(payload["chrome"], "system_frame")
            self.assertEqual(payload["renderer"], "software")


if __name__ == "__main__":
    unittest.main()
