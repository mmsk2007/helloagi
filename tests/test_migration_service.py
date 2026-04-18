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
                json.dumps(
                    {
                        "channels": {"telegram": {"botToken": "123:telegram"}},
                        "gateway": {"auth": {"token": "shared-token"}},
                    }
                ),
                encoding="utf-8",
            )
            report = MigrationImporter().preview("openclaw", str(root))
            self.assertIn("ANTHROPIC_API_KEY", report.secrets_found)
            self.assertIn("TELEGRAM_BOT_TOKEN", report.secrets_found)
            self.assertIn("HELLOAGI_API_KEY", report.secrets_found)

    def test_service_manager_install_records_state(self):
        with TemporaryDirectory() as tmp:
            manager = ServiceManager(
                str(Path(tmp) / "service_state.json"),
                install_root=str(Path(tmp) / "service"),
                platform_name="linux",
                native_control=False,
            )
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
            self.assertEqual(status["backend"], "systemd-user")
            self.assertTrue(status["manifest_path"].endswith(".service"))

    def test_openclaw_apply_imports_workspace_and_approvals(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "openclaw"
            root.mkdir(parents=True, exist_ok=True)
            (root / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-test\n", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "SOUL.md").write_text("# Soul", encoding="utf-8")
            (root / "exec-approvals.json").write_text('{"allow":["git status"]}', encoding="utf-8")
            skills = root / "skills"
            skills.mkdir()
            (skills / "research.md").write_text("# Research flow", encoding="utf-8")

            importer = MigrationImporter(
                import_root=str(Path(tmp) / "imports"),
                skills_dir=str(Path(tmp) / "helloagi-skills"),
            )
            report = importer.apply("openclaw", str(root), rename_imports=True)
            self.assertTrue(report.applied)
            self.assertTrue(any(path.endswith("SOUL.md") for path in report.destination_artifacts))
            self.assertTrue(any(path.endswith("exec-approvals.json") for path in report.destination_artifacts))
            self.assertTrue(any(path.endswith("openclaw-research.md") for path in report.destination_artifacts))


if __name__ == "__main__":
    unittest.main()
