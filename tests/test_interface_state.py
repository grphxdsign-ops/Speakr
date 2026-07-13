from __future__ import annotations

import threading
import unittest

from speakr.interface_state import InterfaceState


class InterfaceStateTests(unittest.TestCase):
    def test_job_retirement_is_generation_guarded_and_atomic(self):
        state = InterfaceState(
            {
                "availability": "ready",
                "pipeline": "error",
                "pipeline_job_id": 12,
                "capture": "listening",
                "capture_job_id": 13,
            }
        )

        self.assertFalse(state.retire_pipeline_job(11, {"error"}))
        self.assertFalse(state.retire_pipeline_job(12, {"error"}))
        self.assertFalse(state.retire_capture_attempt(12))
        self.assertFalse(state.retire_capture_attempt(13))
        state.update(capture="idle")
        self.assertTrue(state.retire_capture_attempt(13))
        self.assertTrue(state.retire_pipeline_job(12, {"error"}))

        snapshot = state.snapshot()
        self.assertEqual(snapshot["capture_job_id"], 0)
        self.assertEqual(snapshot["pipeline_job_id"], 0)
        self.assertEqual(snapshot["pipeline"], "idle")

    def test_snapshot_is_sanitized_and_detached(self):
        state = InterfaceState({"availability": "ready", "hotkey": "right ctrl"})
        snapshot = state.snapshot()
        snapshot["hotkey"] = "changed outside the store"

        self.assertEqual(state.snapshot()["hotkey"], "right ctrl")
        with self.assertRaises(KeyError):
            state.update(transcript="private words")

    def test_capture_outranks_overlapping_pipeline(self):
        state = InterfaceState({"availability": "ready"})
        snapshot = state.update(
            capture="listening",
            capture_job_id=12,
            pipeline="formatting",
            pipeline_job_id=11,
            queue_depth=1,
        )

        self.assertEqual(snapshot["job_id"], 12)
        self.assertEqual(snapshot["capture_job_id"], 12)
        self.assertEqual(snapshot["pipeline_job_id"], 11)
        self.assertEqual(snapshot["primary_text"], "Listening")
        self.assertEqual(
            snapshot["secondary_text"],
            "Previous dictation: Cleaning up locally",
        )

    def test_capture_and_pipeline_keep_independent_edit_modes(self):
        state = InterfaceState({"availability": "ready"})
        snapshot = state.update(
            capture="listening",
            capture_job_id=22,
            capture_mode="dictation",
            pipeline="formatting",
            pipeline_job_id=21,
            pipeline_mode="edit",
        )

        self.assertEqual(snapshot["primary_text"], "Listening")
        self.assertEqual(
            snapshot["secondary_text"],
            "Previous dictation: Applying your instruction locally",
        )

    def test_older_job_error_cannot_replace_a_newer_capture(self):
        state = InterfaceState(
            {
                "availability": "ready",
                "capture": "listening",
                "capture_job_id": 2,
                "pipeline": "error",
                "pipeline_job_id": 1,
            }
        )
        snapshot = state.latch_issue(
            "pipeline_failed",
            "Text was not inserted.",
            "open_log",
            blocking=False,
        )

        self.assertEqual(snapshot["primary_text"], "Listening")
        self.assertIn("Previous dictation", snapshot["secondary_text"])

    def test_issue_latches_selectively_and_discards_exception_detail(self):
        state = InterfaceState({"availability": "ready"})
        snapshot = state.latch_issue(
            "microphone_unavailable",
            "Microphone access is needed.",
            "open_system_settings",
            r"C:\Users\person\private-device-name",
        )

        self.assertEqual(snapshot["availability"], "needs_attention")
        self.assertIsNone(snapshot["last_issue"]["detail"])
        self.assertEqual(snapshot["issue_action"], "open_system_settings")
        self.assertIsNotNone(state.dismiss_issue("different")["last_issue"])
        self.assertIsNone(state.dismiss_issue("microphone_unavailable")["last_issue"])

    def test_wait_and_subscribe_observe_one_versioned_commit(self):
        state = InterfaceState({"availability": "ready"})
        seen = []
        unsubscribe = state.subscribe(seen.append)
        current = state.version

        def publish():
            state.update(pipeline="transcribing", pipeline_job_id=3)

        worker = threading.Thread(target=publish)
        worker.start()
        snapshot = state.wait(current, timeout=1.0)
        worker.join()
        unsubscribe()

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["version"], current + 1)
        self.assertEqual(seen[-1]["version"], snapshot["version"])
        self.assertIsNone(state.wait(snapshot["version"], timeout=0.01))

    def test_success_clears_a_latched_issue(self):
        state = InterfaceState({"availability": "ready"})
        state.latch_issue("pipeline_failed", "Text was not inserted.", "open_log")
        snapshot = state.update(
            availability="ready",
            pipeline="success",
            pipeline_job_id=8,
            status_code="success",
            latest_outcome_code="success",
        )

        self.assertIsNone(snapshot["last_issue"])

    def test_success_preserves_a_restart_notice(self):
        state = InterfaceState({"availability": "ready"})
        state.latch_issue(
            "restart_required",
            "Restart Speakr to use the new microphone setting.",
            "dismiss",
            blocking=False,
        )
        snapshot = state.update(
            pipeline="success",
            pipeline_job_id=9,
            status_code="success",
            latest_outcome_code="success",
        )

        self.assertEqual(snapshot["last_issue"]["code"], "restart_required")
        self.assertEqual(snapshot["primary_text"], "Inserted")
        self.assertEqual(snapshot["latest_outcome"], "Text inserted")


if __name__ == "__main__":
    unittest.main()
