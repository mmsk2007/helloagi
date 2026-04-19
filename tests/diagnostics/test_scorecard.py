import unittest
import tempfile
import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

from agi_runtime.diagnostics.scorecard import run_scorecard


class TestScorecard(unittest.TestCase):
    def _init_db(self, path: Path):
        conn = sqlite3.connect(path)
        try:
            conn.execute("CREATE TABLE schema_migrations (version TEXT)")
            conn.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY)")
            conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
            conn.commit()
        finally:
            conn.close()

    def test_scorecard_runs(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "x.db"
            self._init_db(db_path)
            journal_path = Path(td) / "events.jsonl"
            journal_path.write_text(
                json.dumps({"ts": time.time(), "kind": "input", "payload": {"text": "hi"}}) + "\n",
                encoding="utf-8",
            )
            cfg = Path(td) / "helloagi.json"
            cfg.write_text(json.dumps({"db_path": str(db_path), "journal_path": str(journal_path)}))
            onboard = Path(td) / "onboard.json"
            onboard.write_text(json.dumps({"providers": {"openai_api_key": "sk-test"}}))
            rep = run_scorecard(config_path=str(cfg), onboard_path=str(onboard))
            self.assertIn("grade", rep)
            self.assertIn("checks", rep)
            journal_check = next(check for check in rep["checks"] if check["name"] == "journal")
            self.assertTrue(journal_check["ok"])
            self.assertIn("events=1", journal_check["detail"])
            provider_check = next(check for check in rep["checks"] if check["name"] == "providers")
            self.assertTrue(provider_check["ok"])
            self.assertIn("available=openai", provider_check["detail"])

    def test_scorecard_flags_invalid_journal_lines(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "x.db"
            self._init_db(db_path)
            journal_path = Path(td) / "events.jsonl"
            journal_path.write_text(
                "{bad json}\n"
                + json.dumps({"ts": time.time(), "kind": "failure", "payload": {"code": "tool_timeout"}})
                + "\n",
                encoding="utf-8",
            )
            cfg = Path(td) / "helloagi.json"
            cfg.write_text(json.dumps({"db_path": str(db_path), "journal_path": str(journal_path)}))

            rep = run_scorecard(config_path=str(cfg), onboard_path=str(Path(td) / "onboard.json"))

            journal_check = next(check for check in rep["checks"] if check["name"] == "journal")
            self.assertFalse(journal_check["ok"])
            self.assertIn("invalid_lines=1", journal_check["detail"])
            self.assertIn("failures=1", journal_check["detail"])

    def test_scorecard_flags_stale_journal(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "x.db"
            self._init_db(db_path)
            journal_path = Path(td) / "events.jsonl"
            journal_path.write_text(
                json.dumps({"ts": time.time() - (2 * 24 * 60 * 60), "kind": "input", "payload": {"text": "old"}}) + "\n",
                encoding="utf-8",
            )
            cfg = Path(td) / "helloagi.json"
            cfg.write_text(json.dumps({"db_path": str(db_path), "journal_path": str(journal_path)}))

            rep = run_scorecard(config_path=str(cfg), onboard_path=str(Path(td) / "onboard.json"))

            journal_check = next(check for check in rep["checks"] if check["name"] == "journal")
            self.assertFalse(journal_check["ok"])
            self.assertIn("stale", journal_check["detail"])

    def test_scorecard_flags_missing_providers(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "x.db"
            self._init_db(db_path)
            journal_path = Path(td) / "events.jsonl"
            journal_path.write_text(
                json.dumps({"ts": time.time(), "kind": "input", "payload": {"text": "hi"}}) + "\n",
                encoding="utf-8",
            )
            cfg = Path(td) / "helloagi.json"
            cfg.write_text(json.dumps({"db_path": str(db_path), "journal_path": str(journal_path)}))
            onboard = Path(td) / "onboard.json"
            onboard.write_text(json.dumps({"providers": {}}))

            with patch.dict("os.environ", {}, clear=True):
                rep = run_scorecard(config_path=str(cfg), onboard_path=str(onboard))

            provider_check = next(check for check in rep["checks"] if check["name"] == "providers")
            self.assertFalse(provider_check["ok"])
            self.assertIn("available=none", provider_check["detail"])
            self.assertIn("runtime_backbone=anthropic-missing", provider_check["detail"])

    def test_scorecard_surfaces_env_ready_provider(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "x.db"
            self._init_db(db_path)
            journal_path = Path(td) / "events.jsonl"
            journal_path.write_text(
                json.dumps({"ts": time.time(), "kind": "input", "payload": {"text": "hi"}}) + "\n",
                encoding="utf-8",
            )
            cfg = Path(td) / "helloagi.json"
            cfg.write_text(json.dumps({"db_path": str(db_path), "journal_path": str(journal_path)}))
            onboard = Path(td) / "onboard.json"
            onboard.write_text(json.dumps({"providers": {}}))

            # Length/shape must pass LLM-usable heuristics (short keys are treated as placeholders).
            fake_anthropic = "sk-ant-api03-" + ("a" * 24)
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": fake_anthropic}, clear=True):
                rep = run_scorecard(config_path=str(cfg), onboard_path=str(onboard))

            provider_check = next(check for check in rep["checks"] if check["name"] == "providers")
            self.assertTrue(provider_check["ok"])
            self.assertIn("available=anthropic", provider_check["detail"])
            self.assertIn("runtime_backbone=anthropic-ready", provider_check["detail"])
            self.assertIn("env_llm=anthropic", provider_check["detail"])


if __name__ == '__main__':
    unittest.main()
