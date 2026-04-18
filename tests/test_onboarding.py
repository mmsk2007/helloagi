import unittest
import tempfile
import json
from pathlib import Path

from agi_runtime.onboarding.wizard import OnboardConfig, _to_dict


class TestOnboarding(unittest.TestCase):
    def test_to_dict_shape(self):
        cfg = OnboardConfig()
        d = _to_dict(cfg)
        self.assertIn("agent_name", d)
        self.assertIn("providers", d)
        self.assertIn("service", d)
        self.assertEqual(d["providers"]["active_provider"], "template")

    def test_write_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "onboard.json"
            p.write_text(json.dumps(_to_dict(OnboardConfig())))
            self.assertTrue(p.exists())


if __name__ == '__main__':
    unittest.main()
