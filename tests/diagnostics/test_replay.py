import unittest
import tempfile
import json
from pathlib import Path

from agi_runtime.diagnostics.replay import replay_last_failure


class TestReplay(unittest.TestCase):
    def test_replay_no_failures(self):
        with tempfile.TemporaryDirectory() as td:
            j = Path(td) / "events.jsonl"
            j.write_text(json.dumps({"kind": "input", "payload": {}}) + "\n")
            rep = replay_last_failure(str(j))
            self.assertTrue(rep["ok"])
            self.assertEqual(rep["message"], "no failure events found")
            self.assertEqual(rep["parsed_events"], 1)
            self.assertEqual(rep["skipped_lines"], 0)

    def test_replay_returns_last_failure_with_context_and_previous_input(self):
        with tempfile.TemporaryDirectory() as td:
            j = Path(td) / "events.jsonl"
            entries = [
                {"kind": "input", "payload": {"text": "safe prompt"}},
                {"kind": "response", "payload": {"decision": "allow"}},
                {"kind": "input", "payload": {"text": "risky prompt"}},
                {"kind": "deny", "payload": {"risk": 0.9}},
                {"kind": "response", "payload": {"decision": "fallback"}},
            ]
            j.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")

            rep = replay_last_failure(str(j), context_before=2, context_after=1)

            self.assertTrue(rep["ok"])
            self.assertEqual(rep["failure_kind"], "deny")
            self.assertEqual(rep["failure"]["_line"], 4)
            self.assertEqual(rep["previous_input"]["payload"]["text"], "risky prompt")
            self.assertEqual([event["kind"] for event in rep["context"]], ["response", "input", "deny", "response"])

    def test_replay_skips_invalid_lines(self):
        with tempfile.TemporaryDirectory() as td:
            j = Path(td) / "events.jsonl"
            j.write_text(
                "{bad json}\n"
                + json.dumps({"kind": "input", "payload": {"text": "hello"}})
                + "\n"
                + json.dumps({"kind": "failure", "payload": {"code": "tool_timeout"}})
                + "\n",
                encoding="utf-8",
            )

            rep = replay_last_failure(str(j))

            self.assertTrue(rep["ok"])
            self.assertEqual(rep["failure_kind"], "failure")
            self.assertEqual(rep["parsed_events"], 2)
            self.assertEqual(rep["skipped_lines"], 1)


if __name__ == '__main__':
    unittest.main()
