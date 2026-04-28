"""Tests for multi-provider model routing (tier + env overrides)."""

import os
import unittest

from agi_runtime.models.router import model_id_for_tier, route_for_provider


class TestProviderRouter(unittest.TestCase):
    def tearDown(self):
        for k in (
            "HELLOAGI_OPENAI_MODEL_SPEED",
            "HELLOAGI_OPENAI_MODEL_BALANCED",
            "HELLOAGI_OPENAI_MODEL_QUALITY",
        ):
            os.environ.pop(k, None)

    def test_route_for_provider_openai_default_model(self):
        # Avoid the substring "hi" (matches SPEED_KEYWORDS) which appears inside "hello".
        d = route_for_provider("openai", "status please")
        self.assertEqual(d.tier, "balanced")
        self.assertEqual(d.model, "gpt-4o")
        self.assertIn("reason", d.__dict__)

    def test_model_id_for_tier_openai_env_override(self):
        os.environ["HELLOAGI_OPENAI_MODEL_BALANCED"] = "gpt-4.1-mini"
        self.assertEqual(model_id_for_tier("openai", "balanced"), "gpt-4.1-mini")

    def test_model_id_for_tier_anthropic_ignores_openai_env(self):
        os.environ["HELLOAGI_OPENAI_MODEL_BALANCED"] = "should-not-apply"
        mid = model_id_for_tier("anthropic", "balanced")
        self.assertTrue(mid.startswith("claude-"))

    def test_model_id_for_tier_invalid_tier_falls_back(self):
        self.assertEqual(
            model_id_for_tier("openai", "not-a-tier"),
            model_id_for_tier("openai", "balanced"),
        )


if __name__ == "__main__":
    unittest.main()
