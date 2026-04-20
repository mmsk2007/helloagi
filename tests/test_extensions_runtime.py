import os
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from agi_runtime.extensions.manager import ExtensionManager

ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = ROOT / ".tmp-tests"
TMP_ROOT.mkdir(exist_ok=True)


def _make_scratch_dir() -> Path:
    path = TMP_ROOT / f"ext-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


class TestExtensionsRuntime(unittest.TestCase):
    def test_enable_and_disable_extension(self):
        tmp = _make_scratch_dir()
        try:
            manager = ExtensionManager(str(tmp / "extensions_state.json"))
            enabled = manager.enable("telegram")
            self.assertTrue(enabled.enabled)
            disabled = manager.disable("telegram")
            self.assertFalse(disabled.enabled)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_voice_extension_manifest_is_exposed(self):
        tmp = _make_scratch_dir()
        try:
            manager = ExtensionManager(str(tmp / "extensions_state.json"))
            status = manager.status("voice")
            self.assertEqual(status.name, "voice")
            self.assertEqual(status.category, "channel")
            self.assertIn("helloagi[voice]", status.extras)
            self.assertIsInstance(status.notes, list)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resolve_channel_names_respects_explicit_selection(self):
        tmp = _make_scratch_dir()
        try:
            manager = ExtensionManager(str(tmp / "extensions_state.json"))
            manager.enable("voice")
            names = manager.resolve_channel_names(requested_names=["telegram"], include_enabled=False)
            self.assertEqual(names, ["telegram"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_install_command_is_human_readable(self):
        manager = ExtensionManager()
        self.assertEqual(
            manager.install_command("voice"),
            "python -m agi_runtime.cli extensions install voice",
        )

    def test_doctor_reports_missing_dependencies_or_env(self):
        tmp = _make_scratch_dir()
        manager = ExtensionManager(str(tmp / "extensions_state.json"))
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
            shutil.rmtree(tmp, ignore_errors=True)
