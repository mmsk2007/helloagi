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


if __name__ == '__main__':
    unittest.main()
