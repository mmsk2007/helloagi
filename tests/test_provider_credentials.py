import os
import unittest
from unittest.mock import patch

from agi_runtime.config.providers import provider_env_snapshot, resolve_provider_credential


class TestProviderCredentials(unittest.TestCase):
    def test_prefers_api_key_by_default(self):
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-ant-test", "ANTHROPIC_AUTH_TOKEN": "auth-ant-test"},
            clear=False,
        ):
            credential = resolve_provider_credential("anthropic")
            self.assertTrue(credential.configured)
            self.assertEqual(credential.auth_mode, "api_key")
            self.assertEqual(credential.env_name, "ANTHROPIC_API_KEY")

    def test_can_prefer_auth_token(self):
        with patch.dict(os.environ, {"GOOGLE_AUTH_TOKEN": "google-token"}, clear=False):
            credential = resolve_provider_credential("google", preferred_mode="auth_token")
            self.assertTrue(credential.configured)
            self.assertEqual(credential.auth_mode, "auth_token")
            self.assertEqual(credential.env_name, "GOOGLE_AUTH_TOKEN")

    def test_env_snapshot_tracks_token_mode(self):
        with patch.dict(os.environ, {"OPENAI_AUTH_TOKEN": "openai-token"}, clear=False):
            snapshot = provider_env_snapshot()
            self.assertTrue(snapshot["openai"]["configured"])
            self.assertEqual(snapshot["openai"]["auth_mode"], "auth_token")


if __name__ == "__main__":
    unittest.main()
