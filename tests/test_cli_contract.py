import subprocess
import sys
import unittest
from pathlib import Path

from agi_runtime.core.agent import HelloAGIAgent


ROOT = Path(__file__).resolve().parents[1]


class TestCLIContract(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "agi_runtime.cli", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
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


if __name__ == "__main__":
    unittest.main()
