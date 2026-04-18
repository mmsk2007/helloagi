import unittest
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import patch

from agi_runtime.onboarding.wizard import OnboardConfig, WizardOptions, _to_dict, run_wizard


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

    def test_non_interactive_wizard_creates_auth_profile(self):
        with tempfile.TemporaryDirectory() as td:
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                with patch.dict(
                    os.environ,
                    {
                        "ANTHROPIC_AUTH_TOKEN": "anthropic-token",
                    },
                    clear=False,
                ):
                    with patch(
                        "agi_runtime.onboarding.wizard._run_self_test",
                        return_value={"tools": {"ok": True}, "llm": {"ok": True, "provider": "anthropic", "response": "ok"}},
                    ):
                        run_wizard(
                            "helloagi.onboard.json",
                            WizardOptions(
                                non_interactive=True,
                                runtime_mode="cli",
                                provider="anthropic",
                                auth_mode="auth_token",
                                agent_name="Ava",
                                owner_name="Mina",
                                focus="research",
                                model_tier="quality",
                            ),
                        )
                onboard = json.loads(Path("helloagi.onboard.json").read_text(encoding="utf-8"))
                profiles = json.loads(Path("memory/auth_profiles.json").read_text(encoding="utf-8"))
                self.assertEqual(onboard["providers"]["active_provider"], "anthropic")
                self.assertEqual(onboard["providers"]["active_auth_mode"], "auth_token")
                self.assertEqual(onboard["providers"]["active_profile"], "anthropic-default")
                self.assertEqual(profiles["active_profiles"]["anthropic"], "anthropic-default")
            finally:
                os.chdir(old_cwd)


if __name__ == '__main__':
    unittest.main()
