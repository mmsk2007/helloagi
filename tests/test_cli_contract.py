import subprocess
import sys
import unittest
import os
import shutil
from pathlib import Path
from uuid import uuid4

from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.channels.telegram import _load_telegram_token
from agi_runtime.config.env import load_local_env, save_env_values


ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = ROOT / ".tmp-tests"
TMP_ROOT.mkdir(exist_ok=True)


def _make_scratch_dir() -> Path:
    path = TMP_ROOT / f"cli-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


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

    def test_tools_command_includes_plain_text_risk_legend(self):
        result = self.run_cli("tools", "--policy", "reviewer")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Legend:", result.stdout)
        self.assertIn("low risk", result.stdout)
        self.assertIn("medium risk", result.stdout)
        self.assertIn("high risk", result.stdout)

    def test_context_plan_command_outputs_task_relevant_workspace(self):
        result = self.run_cli("context-plan", "--goal", "Fix checkout bug", "--task-type", "coding")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Context Unrolling Plan", result.stdout)
        self.assertIn("goal: Fix checkout bug", result.stdout)
        self.assertIn("extract_constraints", result.stdout)
        self.assertIn("inspect_failing_tests", result.stdout)
        self.assertNotIn("estimate_depth", result.stdout)
        self.assertIn("workspace_summary:", result.stdout)
        self.assertIn("items_count: 2", result.stdout)
        self.assertIn("observed_items: 1", result.stdout)
        self.assertIn("generated_items: 1", result.stdout)
        self.assertIn("verified_items: 1", result.stdout)
        self.assertIn("primitive_selection", result.stdout)
        self.assertIn("source=primitive_selector", result.stdout)

    def test_context_plan_command_outputs_observed_artifact_references(self):
        result = self.run_cli(
            "context-plan",
            "--goal",
            "Fix tests/test_cli_contract.py::TestCLIContract::test_context_plan and src/agi_runtime/cli.py",
            "--task-type",
            "coding",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("artifact_references", result.stdout)
        self.assertIn("source=primitive:extract_goal_artifact_references", result.stdout)
        self.assertIn("artifact_existence", result.stdout)
        self.assertIn("source=primitive:verify_goal_artifact_references", result.stdout)
        self.assertIn("artifact_metadata", result.stdout)
        self.assertIn("source=primitive:summarize_goal_artifact_metadata", result.stdout)
        self.assertIn("pytest_collection", result.stdout)
        self.assertIn("source=primitive:collect_goal_pytest_references", result.stdout)
        self.assertIn("items_count: 6", result.stdout)
        self.assertIn("observed_items: 5", result.stdout)
        self.assertIn("verified_items: 5", result.stdout)
        self.assertIn("observed=true", result.stdout)
        self.assertIn("verified=true", result.stdout)

    def test_context_plan_operations_task_includes_risk_verification_primitives(self):
        result = self.run_cli(
            "context-plan",
            "--goal",
            "Delete temp build artifacts after confirming scope",
            "--task-type",
            "operations",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("task_type: operations", result.stdout)
        self.assertIn("identify_action_risk", result.stdout)
        self.assertIn("verify_scope", result.stdout)
        self.assertIn("action_gate: high-risk actions require verified generated context", result.stdout)
        self.assertIn("workspace_summary:", result.stdout)
        self.assertIn("primitive_selection", result.stdout)
        self.assertIn("source=primitive_selector", result.stdout)
        self.assertNotIn("estimate_depth", result.stdout)

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
        tmp = _make_scratch_dir()
        env_path = tmp / ".env"
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
            shutil.rmtree(tmp, ignore_errors=True)

    def test_service_help_exposes_extension_flag(self):
        result = self.run_cli("service", "install", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--extension", result.stdout)
        self.assertIn("--voice", result.stdout)

    def test_extensions_help_is_exposed(self):
        result = self.run_cli("extensions", "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("extensions", result.stdout.lower())

    def test_extensions_install_help_is_exposed(self):
        result = self.run_cli("extensions", "install", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("current Python environment", result.stdout)

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
        self.assertIn("--voice", result.stdout)


if __name__ == "__main__":
    unittest.main()
