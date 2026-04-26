import unittest
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from agi_runtime.diagnostics.health import run_health
from agi_runtime.migration.importer import MigrationImporter
from agi_runtime.onboarding.wizard import OnboardConfig, WizardOptions, _to_dict, run_wizard

ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = ROOT / ".tmp-tests"
TMP_ROOT.mkdir(exist_ok=True)


def _make_scratch_dir() -> Path:
    path = TMP_ROOT / f"onboard-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _self_test_all_ok(llm_provider: str = "anthropic"):
    return {
        "tools": {"ok": True, "count": 3},
        "governance": {"ok": True},
        "identity": {"ok": True, "name": "TestAgent"},
        "llm": {"ok": True, "provider": llm_provider, "response": "ok"},
        "skills": {"ok": True},
    }


def _init_minimal_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE schema_migrations (version TEXT)")
        conn.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()


def _init_minimal_journal(path: Path) -> None:
    path.write_text(
        json.dumps({"ts": time.time(), "kind": "input", "payload": {"text": "hi"}}) + "\n",
        encoding="utf-8",
    )


class TestOnboarding(unittest.TestCase):
    def test_to_dict_shape(self):
        cfg = OnboardConfig()
        d = _to_dict(cfg)
        self.assertIn("agent_name", d)
        self.assertIn("providers", d)
        self.assertIn("service", d)
        self.assertEqual(d["providers"]["active_provider"], "template")

    def test_write_file(self):
        td = _make_scratch_dir()
        try:
            p = td / "onboard.json"
            p.write_text(json.dumps(_to_dict(OnboardConfig())))
            self.assertTrue(p.exists())
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_non_interactive_wizard_creates_auth_profile(self):
        td = _make_scratch_dir()
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
                    return_value=_self_test_all_ok("anthropic"),
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
            shutil.rmtree(td, ignore_errors=True)

    def test_non_interactive_google_wizard_creates_auth_profile(self):
        td = _make_scratch_dir()
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            with patch.dict(
                os.environ,
                {"GOOGLE_API_KEY": "google-api-key-test"},
                clear=False,
            ):
                with patch(
                    "agi_runtime.onboarding.wizard._run_self_test",
                    return_value=_self_test_all_ok("google"),
                ):
                    run_wizard(
                        "helloagi.onboard.json",
                        WizardOptions(
                            non_interactive=True,
                            runtime_mode="cli",
                            provider="google",
                            auth_mode="api_key",
                            agent_name="GAgent",
                            owner_name="Owner",
                            focus="coding",
                            model_tier="balanced",
                        ),
                    )
            onboard = json.loads(Path("helloagi.onboard.json").read_text(encoding="utf-8"))
            profiles = json.loads(Path("memory/auth_profiles.json").read_text(encoding="utf-8"))
            self.assertEqual(onboard["providers"]["active_provider"], "google")
            self.assertEqual(onboard["providers"]["active_auth_mode"], "api_key")
            self.assertEqual(onboard["providers"]["active_profile"], "google-default")
            self.assertEqual(profiles["active_profiles"]["google"], "google-default")
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(td, ignore_errors=True)

    def test_non_interactive_import_openclaw_writes_env_and_onboard(self):
        td = _make_scratch_dir()
        old_cwd = os.getcwd()
        fake_oc = td / "fake_openclaw"
        fake_oc.mkdir(parents=True, exist_ok=True)
        (fake_oc / "openclaw.json").write_text(
            json.dumps(
                {
                    "models": {
                        "providers": {
                            "google": {"apiKey": "imported-google-from-oc"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        patched = {**MigrationImporter.DEFAULT_PATHS, "openclaw": fake_oc}
        try:
            os.chdir(td)
            with patch.object(MigrationImporter, "DEFAULT_PATHS", patched):
                with patch(
                    "agi_runtime.onboarding.wizard._run_self_test",
                    return_value=_self_test_all_ok("google"),
                ):
                    run_wizard(
                        "helloagi.onboard.json",
                        WizardOptions(
                            non_interactive=True,
                            runtime_mode="cli",
                            import_source="openclaw",
                            provider="google",
                            auth_mode="api_key",
                            agent_name="Imp",
                            owner_name="User",
                        ),
                    )
            onboard = json.loads(Path("helloagi.onboard.json").read_text(encoding="utf-8"))
            self.assertEqual(onboard.get("migration_source"), "openclaw")
            env_text = Path(".env").read_text(encoding="utf-8")
            self.assertIn("GOOGLE_API_KEY=imported-google-from-oc", env_text.replace("\r\n", "\n"))
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(td, ignore_errors=True)

    def test_non_interactive_import_hermes_writes_env(self):
        td = _make_scratch_dir()
        old_cwd = os.getcwd()
        fake_h = td / "fake_hermes"
        fake_h.mkdir(parents=True, exist_ok=True)
        (fake_h / ".env").write_text(
            "ANTHROPIC_AUTH_TOKEN=hermes-import-token\n",
            encoding="utf-8",
        )
        patched = {**MigrationImporter.DEFAULT_PATHS, "hermes": fake_h}
        try:
            os.chdir(td)
            with patch.object(MigrationImporter, "DEFAULT_PATHS", patched):
                with patch(
                    "agi_runtime.onboarding.wizard._run_self_test",
                    return_value=_self_test_all_ok("anthropic"),
                ):
                    run_wizard(
                        "helloagi.onboard.json",
                        WizardOptions(
                            non_interactive=True,
                            runtime_mode="cli",
                            import_source="hermes",
                            provider="anthropic",
                            auth_mode="auth_token",
                            agent_name="H",
                            owner_name="U",
                        ),
                    )
            onboard = json.loads(Path("helloagi.onboard.json").read_text(encoding="utf-8"))
            self.assertEqual(onboard.get("migration_source"), "hermes")
            env_text = Path(".env").read_text(encoding="utf-8")
            self.assertIn("ANTHROPIC_AUTH_TOKEN=hermes-import-token", env_text.replace("\r\n", "\n"))
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(td, ignore_errors=True)

    def test_health_after_onboard_with_db_and_journal(self):
        td = _make_scratch_dir()
        old_cwd = os.getcwd()
        try:
            os.chdir(td)
            with patch.dict(
                os.environ,
                {"ANTHROPIC_AUTH_TOKEN": "anthropic-token"},
                clear=False,
            ):
                with patch(
                    "agi_runtime.onboarding.wizard._run_self_test",
                    return_value=_self_test_all_ok("anthropic"),
                ):
                    run_wizard(
                        "helloagi.onboard.json",
                        WizardOptions(
                            non_interactive=True,
                            runtime_mode="cli",
                            provider="anthropic",
                            auth_mode="auth_token",
                            agent_name="HealthBot",
                            owner_name="Op",
                        ),
                    )
            _init_minimal_db(Path("memory/helloagi.db"))
            _init_minimal_journal(Path("memory/events.jsonl"))
            rep = run_health(config_path="helloagi.json", onboard_path="helloagi.onboard.json")
            self.assertTrue(rep["checks"]["config_exists"])
            self.assertTrue(rep["checks"]["onboard_exists"])
            self.assertTrue(rep["checks"]["db_exists"])
            self.assertTrue(rep["checks"]["journal_exists"])
            self.assertGreaterEqual(rep["scorecard"]["grade"], 60)
            self.assertTrue(rep["ok"])
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(td, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
