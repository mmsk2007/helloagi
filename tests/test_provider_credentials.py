import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agi_runtime.auth.profiles import AuthProfileManager
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

    def test_auth_profile_beats_plain_local_env(self):
        with TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            old_secret = os.environ.get("CUSTOM_ANTHROPIC_TOKEN")
            old_api_key = os.environ.pop("ANTHROPIC_API_KEY", None)
            old_auth_token = os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
            try:
                os.chdir(tmp)
                Path(".env").write_text("ANTHROPIC_API_KEY=sk-ant-local-env\n", encoding="utf-8")
                os.environ["CUSTOM_ANTHROPIC_TOKEN"] = "anthropic-profile-token"
                AuthProfileManager().ensure_default_profile(
                    "anthropic",
                    "auth_token",
                    "CUSTOM_ANTHROPIC_TOKEN",
                    "Anthropic profile",
                )
                credential = resolve_provider_credential("anthropic")
                self.assertTrue(credential.configured)
                self.assertEqual(credential.auth_mode, "auth_token")
                self.assertEqual(credential.env_name, "CUSTOM_ANTHROPIC_TOKEN")
                self.assertEqual(credential.source, "auth_profile")
            finally:
                os.chdir(old_cwd)
                if old_secret is None:
                    os.environ.pop("CUSTOM_ANTHROPIC_TOKEN", None)
                else:
                    os.environ["CUSTOM_ANTHROPIC_TOKEN"] = old_secret
                if old_api_key is not None:
                    os.environ["ANTHROPIC_API_KEY"] = old_api_key
                if old_auth_token is not None:
                    os.environ["ANTHROPIC_AUTH_TOKEN"] = old_auth_token


if __name__ == "__main__":
    unittest.main()
