import unittest
import tempfile
import json
from pathlib import Path

from agi_runtime.diagnostics.replay import format_replay_report, replay_last_failure


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
                {
                    "kind": "context_workspace_tool_evidence",
                    "payload": {
                        "tool": "file_write",
                        "action_ready": False,
                        "workspace": {
                            "items": [
                                {
                                    "type": "generated_tool_call",
                                    "source": "llm_tool_plan",
                                    "observed": False,
                                    "verified": False,
                                },
                                {
                                    "type": "governance_verification",
                                    "source": "srg",
                                    "observed": True,
                                    "verified": True,
                                },
                            ]
                        },
                    },
                },
                {"kind": "deny", "payload": {"risk": 0.9}},
                {"kind": "response", "payload": {"decision": "fallback"}},
            ]
            j.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")

            rep = replay_last_failure(str(j), context_before=3, context_after=1)

            self.assertTrue(rep["ok"])
            self.assertEqual(rep["failure_kind"], "deny")
            self.assertEqual(rep["failure"]["_line"], 5)
            self.assertEqual(rep["previous_input"]["payload"]["text"], "risky prompt")
            self.assertEqual(
                [event["kind"] for event in rep["context"]],
                ["response", "input", "context_workspace_tool_evidence", "deny", "response"],
            )
            self.assertEqual(rep["latest_context_workspace"]["tool"], "file_write")
            self.assertFalse(rep["latest_context_workspace"]["action_ready"])
            self.assertEqual(
                rep["latest_context_workspace"]["summary"],
                {
                    "items": 2,
                    "observed": 1,
                    "generated": 1,
                    "verified": 1,
                    "unverified_generated": 1,
                    "item_types": ["generated_tool_call", "governance_verification"],
                },
            )

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

    def test_replay_uses_latest_valid_context_workspace_before_failure(self):
        with tempfile.TemporaryDirectory() as td:
            j = Path(td) / "events.jsonl"
            entries = [
                {
                    "kind": "context_workspace_tool_evidence",
                    "payload": {
                        "tool": "file_read",
                        "action_ready": True,
                        "workspace": {
                            "items": [
                                {"type": "observed_user_request", "observed": True, "verified": True},
                            ]
                        },
                    },
                },
                {
                    "kind": "context_workspace_tool_evidence",
                    "payload": {
                        "tool": "file_write",
                        "action_ready": False,
                        "workspace": {"items": "not a list"},
                    },
                },
                {"kind": "deny", "payload": {"risk": 0.9}},
            ]
            j.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")

            rep = replay_last_failure(str(j))

            self.assertEqual(rep["latest_context_workspace"]["tool"], "file_read")
            self.assertTrue(rep["latest_context_workspace"]["action_ready"])
            self.assertEqual(rep["latest_context_workspace"]["summary"]["items"], 1)
            self.assertEqual(rep["latest_context_workspace"]["summary"]["item_types"], ["observed_user_request"])

    def test_format_replay_report_renders_context_workspace_for_humans(self):
        report = {
            "ok": True,
            "failure_kind": "deny",
            "failure": {"_line": 12, "payload": {"risk": 0.9}},
            "previous_input": {"_line": 10, "payload": {"text": "please write a file"}},
            "latest_context_workspace": {
                "tool": "file_write",
                "action_ready": False,
                "line": 11,
                "summary": {
                    "items": 3,
                    "observed": 1,
                    "generated": 2,
                    "verified": 1,
                    "unverified_generated": 2,
                    "item_types": ["generated_tool_call", "governance_verification"],
                },
            },
            "parsed_events": 12,
            "skipped_lines": 0,
        }

        rendered = format_replay_report(report)

        self.assertIn("Last failure: deny at journal line 12", rendered)
        self.assertIn("Previous input: please write a file", rendered)
        self.assertIn("Context workspace evidence:", rendered)
        self.assertIn("tool: file_write", rendered)
        self.assertIn("action ready: no", rendered)
        self.assertIn("items: 3 (observed 1, generated 2, verified 1)", rendered)
        self.assertIn("unverified generated: 2", rendered)
        self.assertIn("item types: generated_tool_call, governance_verification", rendered)


if __name__ == '__main__':
    unittest.main()
