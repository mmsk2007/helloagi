"""SkillManager integration with SkillBank."""

import shutil
import unittest

from agi_runtime.skills.manager import SkillManager


class TestSkillManagerIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = "test_skill_bank_integration_tmp"
        self.sm = SkillManager(
            skills_dir=self.tmp,
            skill_bank_settings={"enabled": True},
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_semantic_matches_return_skill_match(self) -> None:
        self.sm.create_skill(
            name="report-gen",
            description="Generate quarterly reports from spreadsheets",
            triggers=["report", "quarter"],
            tools=["file_read"],
            steps=["Load data", "Summarize"],
        )
        matches = self.sm.find_matching_skill_semantic("need a quarterly report from csv", top_k=2)
        self.assertTrue(matches)
        self.assertGreaterEqual(matches[0].relevance, 0.1)


if __name__ == "__main__":
    unittest.main()
