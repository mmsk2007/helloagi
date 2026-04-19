import subprocess
import sys
import unittest
import os
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import agi_runtime.cli as cli_module
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.channels.telegram import _load_telegram_token
from agi_runtime.config.env import load_local_env, save_env_values


ROOT = Path(__file__).resolve().parents[1]


class TestCLIContract(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "agi_runtime.cli", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_run_help_exposes_policy_flag(self):
        result = self.run_cli("run", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--policy", result.stdout)

    def test_root_help_lists_lifecycle_commands(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("update", result.stdout)
        self.assertIn("uninstall", result.stdout)
        self.assertIn("service", result.stdout)
        self.assertIn("health", result.stdout)
        self.assertIn("migrate", result.stdout)
        self.assertIn("extensions", result.stdout)
        self.assertIn("runs", result.stdout)
        self.assertIn("auth", result.stdout)

    def test_tools_command_does_not_crash_on_windows_encoding(self):
        result = self.run_cli("tools", "--policy", "reviewer")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[", result.stdout)

    def test_uninstall_requires_explicit_confirmation(self):
        result = self.run_cli("uninstall")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--yes", result.stdout)

    def test_policy_pack_filters_visible_tools(self):
        agent = HelloAGIAgent(policy_pack="reviewer")
        info = agent.get_tools_info()
        self.assertIn("file_read", info)
        self.assertNotIn("bash_exec", info)
        self.assertNotIn("file_write", info)

    def test_local_env_round_trip_for_telegram_token(self):
        with TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            old = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            try:
                save_env_values({"TELEGRAM_BOT_TOKEN": "123:token"}, str(env_path))
                load_local_env(str(env_path))
                self.assertEqual(_load_telegram_token(), "123:token")
            finally:
                if old is None:
                    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
                else:
                    os.environ["TELEGRAM_BOT_TOKEN"] = old

    def test_service_help_exposes_extension_flag(self):
        result = self.run_cli("service", "install", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--extension", result.stdout)

    def test_extensions_help_is_exposed(self):
        result = self.run_cli("extensions", "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("extensions", result.stdout.lower())

    def test_onboard_help_exposes_non_interactive_flags(self):
        result = self.run_cli("onboard", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--non-interactive", result.stdout)
        self.assertIn("--enable-extension", result.stdout)

    def test_runs_help_exposes_export_subcommand(self):
        result = self.run_cli("runs", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("export", result.stdout)

    def test_auth_list_command_is_exposed(self):
        result = self.run_cli("auth", "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("profiles", result.stdout)

    def test_serve_help_exposes_require_auth(self):
        result = self.run_cli("serve", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--require-auth", result.stdout)

    def test_setup_serve_logging_respects_documented_levels(self):
        original_handlers = logging.root.handlers[:]
        original_level = logging.root.level
        old_marker = os.environ.pop("HELLOAGI_SERVE_LOG_INSTALLED", None)
        try:
            for handler in original_handlers:
                logging.root.removeHandler(handler)

            cli_module._setup_serve_logging(verbose=0, quiet=False)
            self.assertEqual(logging.root.level, logging.WARNING)

            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)
            os.environ.pop("HELLOAGI_SERVE_LOG_INSTALLED", None)

            cli_module._setup_serve_logging(verbose=1, quiet=False)
            self.assertEqual(logging.root.level, logging.INFO)

            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)
            os.environ.pop("HELLOAGI_SERVE_LOG_INSTALLED", None)

            cli_module._setup_serve_logging(verbose=2, quiet=False)
            self.assertEqual(logging.root.level, logging.DEBUG)

            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)
            os.environ.pop("HELLOAGI_SERVE_LOG_INSTALLED", None)

            cli_module._setup_serve_logging(verbose=2, quiet=True)
            self.assertEqual(logging.root.level, logging.ERROR)
        finally:
            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)
            for handler in original_handlers:
                logging.root.addHandler(handler)
            logging.root.setLevel(original_level)
            if old_marker is None:
                os.environ.pop("HELLOAGI_SERVE_LOG_INSTALLED", None)
            else:
                os.environ["HELLOAGI_SERVE_LOG_INSTALLED"] = old_marker


if __name__ == "__main__":
    unittest.main()
