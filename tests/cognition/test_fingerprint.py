import unittest

from agi_runtime.cognition.fingerprint import (
    normalize_task_text,
    task_fingerprint,
)


class TestNormalize(unittest.TestCase):
    def test_lowercases_and_collapses_whitespace(self):
        self.assertEqual(
            normalize_task_text("  Send   the    File  "),
            "send the file",
        )

    def test_strips_trivial_punctuation(self):
        self.assertEqual(
            normalize_task_text("Send the file, please!"),
            "send the file please",
        )

    def test_empty_input(self):
        self.assertEqual(normalize_task_text(""), "")
        self.assertEqual(normalize_task_text("   "), "")


class TestFingerprint(unittest.TestCase):
    def test_paraphrase_collisions_within_normalization(self):
        # Same content, different casing/punctuation/whitespace → same fingerprint.
        a = task_fingerprint("Summarize the report.")
        b = task_fingerprint("  summarize    the report  ")
        c = task_fingerprint("SUMMARIZE THE REPORT!!!")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_different_tasks_diverge(self):
        a = task_fingerprint("summarize the report")
        b = task_fingerprint("delete the report")
        self.assertNotEqual(a, b)

    def test_task_type_discriminates(self):
        a = task_fingerprint("run it", task_type="coding")
        b = task_fingerprint("run it", task_type="file_ops")
        self.assertNotEqual(a, b)

    def test_tool_hints_order_independent(self):
        a = task_fingerprint("publish", tool_hints=["git", "ssh"])
        b = task_fingerprint("publish", tool_hints=["ssh", "git"])
        self.assertEqual(a, b)

    def test_fingerprint_is_16_chars(self):
        self.assertEqual(len(task_fingerprint("anything")), 16)


if __name__ == "__main__":
    unittest.main()
