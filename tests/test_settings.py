import json
import unittest
import tempfile
from pathlib import Path

from agi_runtime.config.settings import load_settings


class TestSettings(unittest.TestCase):
    def test_load_creates_default(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "helloagi.json"
            s = load_settings(str(p))
            self.assertTrue(p.exists())
            self.assertEqual(s.name, "HelloAGI")
            self.assertTrue(s.reliability.get("enabled", True))

    def test_partial_feature_dicts_merge(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "helloagi.json"
            p.write_text(json.dumps({"reliability": {"enabled": False}, "name": "X"}))
            s = load_settings(str(p))
            self.assertFalse(s.reliability["enabled"])
            self.assertEqual(s.reliability.get("loop_threshold"), 3)
            self.assertEqual(s.reliability.get("soft_timeout_sec"), 0)
            self.assertEqual(s.name, "X")


if __name__ == '__main__':
    unittest.main()
