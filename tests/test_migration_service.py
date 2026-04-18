import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agi_runtime.migration.importer import MigrationImporter
from agi_runtime.service.manager import ServiceManager


class TestMigrationAndService(unittest.TestCase):
    def test_openclaw_preview_reads_env_and_json(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-test\n", encoding="utf-8")
            (root / "openclaw.json").write_text(
                json.dumps({"channels": {"telegram": {"botToken": "123:telegram"}}}),
                encoding="utf-8",
            )
            report = MigrationImporter().preview("openclaw", str(root))
            self.assertIn("ANTHROPIC_API_KEY", report.found)
            self.assertIn("TELEGRAM_BOT_TOKEN", report.found)

    def test_service_manager_install_records_state(self):
        with TemporaryDirectory() as tmp:
            manager = ServiceManager(str(Path(tmp) / "service_state.json"))
            cfg = manager.install(
                host="127.0.0.1",
                port=9900,
                config_path="helloagi.json",
                policy_pack="reviewer",
                telegram=True,
                discord=False,
            )
            self.assertTrue(cfg.installed)
            status = manager.status()
            self.assertTrue(status["installed"])
            self.assertEqual(status["port"], 9900)
            self.assertTrue(status["telegram"])


if __name__ == "__main__":
    unittest.main()
