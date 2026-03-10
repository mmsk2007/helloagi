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


if __name__ == '__main__':
    unittest.main()
