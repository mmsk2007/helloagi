import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agi_runtime.auth.profiles import AuthProfileManager


class TestAuthProfiles(unittest.TestCase):
    def test_activate_and_resolve_profile(self):
        with TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            old_secret = os.environ.get("CUSTOM_GOOGLE_TOKEN")
            try:
                os.chdir(tmp)
                os.environ["CUSTOM_GOOGLE_TOKEN"] = "google-profile-token"
                manager = AuthProfileManager()
                manager.upsert_profile(
                    name="google-default",
                    provider="google",
                    auth_mode="auth_token",
                    env_key="CUSTOM_GOOGLE_TOKEN",
                    make_active=True,
                )
                resolved = manager.resolve("google")
                self.assertTrue(resolved["configured"])
                self.assertEqual(resolved["name"], "google-default")
                self.assertEqual(resolved["env_name"], "CUSTOM_GOOGLE_TOKEN")
            finally:
                os.chdir(old_cwd)
                if old_secret is None:
                    os.environ.pop("CUSTOM_GOOGLE_TOKEN", None)
                else:
                    os.environ["CUSTOM_GOOGLE_TOKEN"] = old_secret

    def test_doctor_reports_local_env_source(self):
        with TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                Path(".env").write_text("CUSTOM_OPENAI_TOKEN=openai-local-token\n", encoding="utf-8")
                manager = AuthProfileManager()
                manager.upsert_profile(
                    name="openai-default",
                    provider="openai",
                    auth_mode="auth_token",
                    env_key="CUSTOM_OPENAI_TOKEN",
                    make_active=True,
                )
                report = manager.doctor()
                self.assertEqual(report["total"], 1)
                self.assertEqual(report["profiles"][0]["source"], "local_env")
                self.assertTrue(report["profiles"][0]["configured"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
