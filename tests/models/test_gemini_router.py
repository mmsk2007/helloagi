import os
import unittest
from unittest.mock import patch

from agi_runtime.models.gemini_router import route_gemini_model


class TestGeminiRouter(unittest.TestCase):
    def test_env_override_wins(self):
        with patch.dict(os.environ, {"HELLOAGI_GOOGLE_MODEL": "gemini-flash-latest"}, clear=False):
            decision = route_gemini_model("hello")
        self.assertEqual(decision.model, "gemini-flash-latest")
        self.assertEqual(decision.reason, "env-override")

    def test_settings_tier_quality_prefers_quality_model(self):
        with patch.dict(os.environ, {}, clear=True):
            decision = route_gemini_model("say hi", default_tier="quality")
        self.assertEqual(decision.reason, "settings-tier-quality")
        self.assertIn("pro", decision.model)

    def test_settings_tier_speed_prefers_fast_model(self):
        with patch.dict(os.environ, {}, clear=True):
            decision = route_gemini_model("say hi", default_tier="speed")
        self.assertEqual(decision.reason, "settings-tier-speed")
        self.assertIn("flash-lite", decision.model)


if __name__ == "__main__":
    unittest.main()
