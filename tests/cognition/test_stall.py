"""StallDetector — mid-loop floundering guard tests.

Covers:
- Silent tool-only turns accumulate; narration resets the streak.
- The detector waits past ``warm_up_tool_calls`` before firing.
- ``acknowledge()`` makes the signal one-shot per streak.
- ``build_reminder`` formats a usable user-message string.
- ``detector_from_config`` reads config sub-dict cleanly.
"""

import unittest

from agi_runtime.cognition.stall import (
    StallDetector,
    build_reminder,
    detector_from_config,
)


class TestStallDetector(unittest.TestCase):
    def test_silent_streak_fires_after_budget(self):
        det = StallDetector(silent_turn_budget=3, warm_up_tool_calls=2)
        # 4 tool calls done first to clear warm-up, but with narration
        # → no streak.
        det.observe(text_chars=200, tool_call_count=2)
        det.observe(text_chars=200, tool_call_count=2)
        self.assertFalse(det.check().detected)
        # Now 3 silent tool turns in a row.
        det.observe(text_chars=0, tool_call_count=1)
        det.observe(text_chars=10, tool_call_count=1)
        det.observe(text_chars=5, tool_call_count=1)
        sig = det.check()
        self.assertTrue(sig.detected)
        self.assertEqual(sig.consecutive_silent_turns, 3)

    def test_narration_resets_streak(self):
        det = StallDetector(silent_turn_budget=2, warm_up_tool_calls=0)
        det.observe(text_chars=0, tool_call_count=1)
        # Narration mid-stream — reset.
        det.observe(text_chars=500, tool_call_count=1)
        det.observe(text_chars=0, tool_call_count=1)
        # Streak is 1, not 2 — should NOT fire.
        self.assertFalse(det.check().detected)

    def test_warm_up_blocks_early_fire(self):
        det = StallDetector(silent_turn_budget=2, warm_up_tool_calls=10)
        # Even with silent streak met, total tool calls below warm_up.
        det.observe(text_chars=0, tool_call_count=1)
        det.observe(text_chars=0, tool_call_count=1)
        det.observe(text_chars=0, tool_call_count=1)
        self.assertFalse(det.check().detected)

    def test_acknowledge_makes_signal_one_shot(self):
        det = StallDetector(silent_turn_budget=2, warm_up_tool_calls=0)
        det.observe(text_chars=0, tool_call_count=1)
        det.observe(text_chars=0, tool_call_count=1)
        self.assertTrue(det.check().detected)
        det.acknowledge()
        # Without a fresh silent turn or reset, we don't keep firing.
        self.assertFalse(det.check().detected)

    def test_no_tool_calls_doesnt_count_as_silent(self):
        det = StallDetector(silent_turn_budget=2, warm_up_tool_calls=0)
        # Pure thinking turn — not a stall, even with no text.
        det.observe(text_chars=0, tool_call_count=0)
        det.observe(text_chars=0, tool_call_count=0)
        self.assertFalse(det.check().detected)

    def test_build_reminder_includes_counts(self):
        det = StallDetector(silent_turn_budget=2, warm_up_tool_calls=0)
        det.observe(text_chars=0, tool_call_count=3)
        det.observe(text_chars=0, tool_call_count=2)
        sig = det.check()
        self.assertTrue(sig.detected)
        msg = build_reminder(sig)
        self.assertIn("turn-budget-warning", msg)
        self.assertIn("5", msg)  # total tool calls
        self.assertIn("2", msg)  # silent turns

    def test_detector_from_config_reads_sub_dict(self):
        det = detector_from_config({
            "stall": {"silent_turn_budget": 7, "warm_up_tool_calls": 1, "text_threshold": 99}
        })
        self.assertEqual(det.silent_turn_budget, 7)
        self.assertEqual(det.warm_up_tool_calls, 1)
        self.assertEqual(det.text_threshold, 99)

    def test_detector_from_config_defaults_when_missing(self):
        det = detector_from_config({})
        self.assertGreaterEqual(det.silent_turn_budget, 1)
        self.assertGreaterEqual(det.warm_up_tool_calls, 0)


if __name__ == "__main__":
    unittest.main()
