import tempfile
import unittest
import subprocess
from pathlib import Path

from agi_runtime.diagnostics.public_readiness import (
    format_public_readiness,
    run_public_readiness,
)


class TestPublicReadiness(unittest.TestCase):
    def _git(self, repo: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

    def _write(self, repo: Path, rel: str, text: str = "") -> None:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def _init_repo(self, repo: Path) -> None:
        self._git(repo, "init")
        self._git(repo, "config", "user.email", "test@example.invalid")
        self._git(repo, "config", "user.name", "Test User")
        self._write(repo, ".gitignore", ".env\nhelloagi.json\nhelloagi.onboard.json\n/memory/\nOPS_STATUS.md\nPAUSED_AUTOMATIONS.md\n")
        self._write(repo, "README.md", "helloagi tools helloagi service install HELLOAGI_TELEGRAM_LIVE\n")
        self._write(repo, "pyproject.toml", "[project]\nname='helloagi'\n")
        self._write(repo, "scripts/install.sh", "#!/usr/bin/env bash\n")
        self._write(repo, "scripts/install.ps1", "Write-Host hello\n")
        for doc in [
            "docs/install.md",
            "docs/cli-reference.md",
            "docs/channels.md",
            "docs/deployment.md",
            "docs/environment.md",
            "docs/security.md",
            "docs/privacy.md",
            "docs/troubleshooting.md",
            "docs/production-checklist.md",
            "docs/streaming-contract.md",
            "docs/providers.md",
            "docs/reminders-scheduling.md",
            "docs/organism-architecture.md",
            "docs/plans/bioagent-organism-intelligence-phases.md",
        ]:
            self._write(repo, doc, "TelegramStreamConsumer HELLOAGI_TELEGRAM_GROUP_MODE providers.py memory/ reminders runs export /remind brain cortex nervous senses effectors immune metabolism homeostasis growth scorecard\n")
        self._write(repo, "src/agi_runtime/channels/telegram.py", "HELLOAGI_TELEGRAM_GROUP_MODE TelegramStreamConsumer\n")
        self._write(repo, "src/agi_runtime/service/manager.py", "service/manager.py\n")
        self._write(repo, "src/agi_runtime/config/providers.py", "providers.py\n")
        self._write(repo, "src/agi_runtime/tools/builtins/memory_store.py", "memory_store\n")
        self._write(repo, "tests/test_smoke.py", "def test_smoke():\n    assert True\n")
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", "init")

    def test_public_readiness_passes_for_clean_generic_repo(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._init_repo(repo)

            report = run_public_readiness(repo)

            self.assertTrue(report["ready"], report)
            self.assertEqual(report["grade"], 100)
            rendered = format_public_readiness(report)
            self.assertIn("READY", rendered)

    def test_public_readiness_blocks_tracked_runtime_and_private_values(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._init_repo(repo)
            self._write(repo, "memory/identity_state.json", "{}")
            self._git(repo, "add", "-f", "memory/identity_state.json")
            leaked_token = "TELEGRAM_BOT_" + "TOKEN=" + "123456789" + ":" + "abcdefghijklmnopqrstuvwxyz"
            self._write(repo, "docs/leak.md", leaked_token + "\n")
            self._git(repo, "add", "docs/leak.md")
            self._git(repo, "commit", "-m", "bad")

            report = run_public_readiness(repo)

            self.assertFalse(report["ready"])
            self.assertIn("tracked_runtime_artifacts", report["blockers"])
            self.assertIn("private_text_scan", report["blockers"])

    def test_public_readiness_reports_missing_docs(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._init_repo(repo)
            (repo / "docs" / "privacy.md").unlink()
            self._git(repo, "add", "-u")
            self._git(repo, "commit", "-m", "remove privacy")

            report = run_public_readiness(repo)

            self.assertFalse(report["ready"])
            self.assertIn("public_docs", report["blockers"])

    def test_public_readiness_reports_missing_organism_architecture(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._init_repo(repo)
            (repo / "docs" / "organism-architecture.md").unlink()
            self._git(repo, "add", "-u")
            self._git(repo, "commit", "-m", "remove organism architecture")

            report = run_public_readiness(repo)

            self.assertFalse(report["ready"])
            self.assertIn("organism_architecture", report["blockers"])

    def test_public_readiness_flags_secret_like_filenames(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._init_repo(repo)
            self._write(repo, "secrets.json", "{}")
            self._git(repo, "add", "secrets.json")
            self._git(repo, "commit", "-m", "add accidental secret file")

            report = run_public_readiness(repo)

            self.assertFalse(report["ready"])
            self.assertIn("tracked_runtime_artifacts", report["blockers"])

    def test_public_readiness_can_allow_dirty_checkout_for_precommit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            self._init_repo(repo)
            self._write(repo, "docs/new.md", "draft")

            clean_required = run_public_readiness(repo)
            dirty_allowed = run_public_readiness(repo, require_clean=False)

            self.assertIn("working_tree_clean_for_release", clean_required["blockers"])
            self.assertTrue(dirty_allowed["ready"], dirty_allowed)


if __name__ == "__main__":
    unittest.main()
