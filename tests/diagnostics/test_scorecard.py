import unittest
import tempfile
import json
from pathlib import Path

from agi_runtime.diagnostics.scorecard import run_scorecard


class TestScorecard(unittest.TestCase):
    def test_scorecard_runs(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "helloagi.json"
            cfg.write_text(json.dumps({"db_path": str(Path(td) / "x.db"), "journal_path": str(Path(td) / "events.jsonl")}))
            rep = run_scorecard(config_path=str(cfg), onboard_path=str(Path(td) / "onboard.json"))
            self.assertIn("grade", rep)
            self.assertIn("checks", rep)


if __name__ == '__main__':
    unittest.main()
