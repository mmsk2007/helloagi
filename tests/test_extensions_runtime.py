import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agi_runtime.extensions.manager import ExtensionManager


class TestExtensionsRuntime(unittest.TestCase):
    def test_enable_and_disable_extension(self):
        with TemporaryDirectory() as tmp:
            manager = ExtensionManager(str(Path(tmp) / "extensions_state.json"))
            enabled = manager.enable("telegram")
            self.assertTrue(enabled.enabled)
            disabled = manager.disable("telegram")
            self.assertFalse(disabled.enabled)

    def test_doctor_reports_missing_dependencies_or_env(self):
        with TemporaryDirectory() as tmp:
            manager = ExtensionManager(str(Path(tmp) / "extensions_state.json"))
            old = os.environ.pop("DISCORD_BOT_TOKEN", None)
            try:
                manager.enable("discord")
                report = manager.doctor(enabled_only=True)
                self.assertEqual(report["enabled"], 1)
                self.assertEqual(report["extensions"][0]["name"], "discord")
                self.assertIn("DISCORD_BOT_TOKEN", report["extensions"][0]["missing_env"])
            finally:
                if old is not None:
                    os.environ["DISCORD_BOT_TOKEN"] = old
