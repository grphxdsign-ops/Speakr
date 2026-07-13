from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from speakr.config import Config
from speakr.dictionary import Dictionary


class ConfigTests(unittest.TestCase):
    def test_ui_defaults_merge_without_replacing_existing_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"hotkey": "space", "ui": {"theme": "dark"}}),
                encoding="utf-8",
            )

            config = Config(path)

            self.assertEqual(config.get("hotkey"), "space")
            self.assertEqual(config.get("ui", "theme"), "dark")
            self.assertEqual(config.get("ui", "visual_effects"), "system")
            self.assertEqual(config.get("ui", "text_scale"), "system")
            self.assertEqual(config.get("ui", "reduced_motion"), "system")
            self.assertEqual(config.get("ui", "hud_visibility"), "while_dictating")

    def test_preview_motion_key_migrates_to_reduced_motion_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"ui": {"motion": "reduced"}}),
                encoding="utf-8",
            )

            config = Config(path)

            self.assertEqual(config.get("ui", "reduced_motion"), "reduce")

    def test_failed_atomic_replace_keeps_previous_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = Config(path)
            before = path.read_bytes()
            config.data["hotkey"] = "space"

            with mock.patch("speakr.config.os.replace", side_effect=OSError("full")):
                with self.assertRaises(OSError):
                    config.save()

            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_single_setting_failure_rolls_back_memory_and_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = Config(path)
            before_disk = path.read_bytes()
            before_memory = config.snapshot()

            with mock.patch("speakr.config.os.replace", side_effect=OSError("full")):
                with self.assertRaises(OSError):
                    config.set("log_transcripts", value=True)

            self.assertEqual(config.snapshot(), before_memory)
            self.assertEqual(path.read_bytes(), before_disk)

    def test_grouped_setting_failure_rolls_back_memory_and_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = Config(path)
            before_disk = path.read_bytes()
            before_memory = config.snapshot()

            with mock.patch("speakr.config.os.replace", side_effect=OSError("full")):
                with self.assertRaises(OSError):
                    config.set_many({"ui.theme": "dark", "ui.text_scale": 200})

            self.assertEqual(config.snapshot(), before_memory)
            self.assertEqual(path.read_bytes(), before_disk)


class DictionaryTests(unittest.TestCase):
    def test_ui_edits_preserve_comments_order_blanks_and_unknown_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dictionary.txt"
            original = (
                "# keep this heading\n"
                "Alpha\n"
                "\n"
                "unusual line with spaces\n"
                "heard => Intended\n"
                "# keep this footer\n"
                "\n"
            )
            path.write_text(original, encoding="utf-8")
            dictionary = Dictionary(path)

            dictionary.add_hint("Beta")
            after_add = path.read_text(encoding="utf-8")

            self.assertTrue(after_add.startswith(original))
            self.assertTrue(after_add.endswith("Beta\n"))
            self.assertLess(after_add.index("Alpha"), after_add.index("heard => Intended"))
            self.assertIn("# keep this footer\n\nBeta", after_add)

            beta_id = next(
                entry["id"] for entry in dictionary.entries() if entry.get("word") == "Beta"
            )
            dictionary.remove_entry(beta_id)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_failed_atomic_replace_keeps_previous_dictionary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dictionary.txt"
            path.write_text("# local\nSpeakr\n", encoding="utf-8")
            dictionary = Dictionary(path)
            before = path.read_bytes()

            with mock.patch("speakr.dictionary.os.replace", side_effect=OSError("full")):
                with self.assertRaises(OSError):
                    dictionary.add_hint("NewWord")

            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_stale_entry_id_never_deletes_a_different_raw_file_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dictionary.txt"
            path.write_text("Alpha\nBeta\n", encoding="utf-8")
            dictionary = Dictionary(path)
            beta_id = next(
                entry["id"] for entry in dictionary.entries() if entry.get("word") == "Beta"
            )

            path.write_text("Inserted above\nAlpha\nBeta\n", encoding="utf-8")
            dictionary.remove_entry(beta_id)
            self.assertEqual(path.read_text(encoding="utf-8"), "Inserted above\nAlpha\n")

            dictionary = Dictionary(path)
            alpha_id = next(
                entry["id"] for entry in dictionary.entries() if entry.get("word") == "Alpha"
            )
            path.write_text("Inserted above\nChanged Alpha\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed|no longer"):
                dictionary.remove_entry(alpha_id)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "Inserted above\nChanged Alpha\n",
            )


if __name__ == "__main__":
    unittest.main()
