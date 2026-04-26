import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agi_runtime.migration.importer import MigrationImporter
from agi_runtime.service.manager import ServiceConfig, ServiceManager


class TestMigrationAndService(unittest.TestCase):
    def test_service_command_python_is_absolute(self):
        manager = ServiceManager(native_control=False)
        cfg = ServiceConfig(
            workdir=str(Path.cwd()),
            host="127.0.0.1",
            port=8787,
            config_path="helloagi.json",
            policy_pack="safe-default",
            enabled_extensions=["telegram"],
            auth_required=True,
        )
        cmd = manager._service_command(cfg)
        self.assertTrue(Path(cmd[0]).is_absolute(), msg=f"expected absolute python, got {cmd[0]!r}")
        self.assertEqual(cmd[1], "-m")
        self.assertEqual(cmd[2], "agi_runtime.cli")
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
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
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
                self.assertTrue(status["auth_required"])
                self.assertEqual(status["auth_env_key"], "HELLOAGI_API_KEY")
                manifest = Path(status["manifest_path"]).read_text(encoding="utf-8")
                self.assertIn("--require-auth", manifest)
            finally:
                os.chdir(old_cwd)

    def test_service_start_requires_configured_auth_token(self):
        with TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            manager = ServiceManager(
                str(Path(tmp) / "service_state.json"),
                install_root=str(Path(tmp) / "service"),
                platform_name="linux",
                native_control=False,
            )
            cfg = manager.load()
            cfg.installed = True
            cfg.auth_required = True
            cfg.auth_env_key = "HELLOAGI_API_KEY"
            manager.save(cfg)
            old = os.environ.pop("HELLOAGI_API_KEY", None)
            try:
                with self.assertRaises(RuntimeError):
                    manager.start()
            finally:
                os.chdir(old_cwd)
                if old is not None:
                    os.environ["HELLOAGI_API_KEY"] = old

    def test_openclaw_apply_imports_workspace_and_approvals(self):
        with TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
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
                profiles_path = Path("memory/auth_profiles.json")
                self.assertTrue(profiles_path.exists())
                profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
                self.assertEqual(profiles["active_profiles"]["anthropic"], "anthropic-default")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
