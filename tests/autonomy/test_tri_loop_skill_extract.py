"""TriLoop skill extraction on successful runs."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agi_runtime.autonomy.tri_loop import TriLoop
from agi_runtime.skills.skill_bank import SkillBank


def _no_anthropic():
    os.environ.pop("ANTHROPIC_API_KEY", None)


class StubAgent:
    def __init__(self):
        from agi_runtime.governance.srg import SRGGovernor

        self.governor = SRGGovernor()

    def think(self, prompt: str):
        class R:
            text = f"done: {prompt}"
            tool_calls_made = 1

        return R()


class TestTriLoopSkillExtract(unittest.TestCase):
    def setUp(self) -> None:
        _no_anthropic()

    def test_passed_run_adds_skill_when_bank_configured(self) -> None:
        with TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            skills_dir.mkdir()
            bank = SkillBank(str(skills_dir))
            loop = TriLoop(
                StubAgent(),
                skill_bank=bank,
                skill_governance_adapter=None,
                skill_auto_extract=True,
            )
            r = loop.run("Write a summary of yesterday's standup.")
            self.assertEqual(r.status, "passed")
            self.assertGreaterEqual(bank.count, 1)


if __name__ == "__main__":
    unittest.main()
