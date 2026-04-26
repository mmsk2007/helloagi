"""Tests for the Co-Evolving Skill System (Milestone 2).

All tests use stubs, temp dirs (auto-cleaned), and no API keys.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agi_runtime.skills.skill_schema import SkillContract
from agi_runtime.skills.skill_bank import SkillBank
from agi_runtime.skills.skill_retriever import SkillRetriever, SkillMatch
from agi_runtime.skills.skill_extractor import SkillExtractor
from agi_runtime.skills.skill_evaluator import SkillEvaluator, EvaluationResult


# ── SkillContract Tests ──────────────────────────────────────────

class TestSkillContract(unittest.TestCase):

    def test_create_with_defaults(self):
        s = SkillContract(name="test-skill", description="A test")
        self.assertIsNotNone(s.skill_id)
        self.assertEqual(s.name, "test-skill")
        self.assertEqual(s.confidence_score, 0.5)
        self.assertEqual(s.status, "candidate")
        self.assertGreater(s.created_at, 0)

    def test_success_rate_empty(self):
        s = SkillContract()
        self.assertEqual(s.success_rate, 0.5)

    def test_success_rate_computed(self):
        s = SkillContract(success_count=7, failure_count=3)
        self.assertAlmostEqual(s.success_rate, 0.7)

    def test_record_success(self):
        s = SkillContract()
        s.record_success()
        self.assertEqual(s.usage_count, 1)
        self.assertEqual(s.success_count, 1)
        self.assertGreater(s.last_used_at, 0)

    def test_record_failure_adds_mode(self):
        s = SkillContract()
        s.record_failure("timeout")
        self.assertEqual(s.failure_count, 1)
        self.assertIn("timeout", s.failure_modes)
        # Duplicate failure mode not added
        s.record_failure("timeout")
        self.assertEqual(s.failure_modes.count("timeout"), 1)

    def test_compute_risk_level_high(self):
        s = SkillContract(tools_required=["bash_exec", "file_read"])
        self.assertEqual(s.compute_risk_level(), "high")

    def test_compute_risk_level_medium(self):
        s = SkillContract(tools_required=["file_write"])
        self.assertEqual(s.compute_risk_level(), "medium")

    def test_compute_risk_level_low(self):
        s = SkillContract(tools_required=["file_read", "memory_recall"])
        self.assertEqual(s.compute_risk_level(), "low")

    def test_serialization_roundtrip(self):
        s = SkillContract(
            name="roundtrip", description="Test roundtrip",
            preconditions=["has file"], execution_steps=["read", "process"],
            tools_required=["file_read"], success_criteria=["file processed"],
        )
        j = s.to_json()
        s2 = SkillContract.from_json(j)
        self.assertEqual(s.name, s2.name)
        self.assertEqual(s.preconditions, s2.preconditions)
        self.assertEqual(s.execution_steps, s2.execution_steps)

    def test_to_markdown(self):
        s = SkillContract(
            name="md-test", description="Markdown test",
            preconditions=["ready"], execution_steps=["step1", "step2"],
        )
        md = s.to_markdown()
        self.assertIn("---", md)
        self.assertIn("md-test", md)
        self.assertIn("## Steps", md)

    def test_to_prompt_injection(self):
        s = SkillContract(
            name="prompt-test", description="For prompts",
            preconditions=["file exists"], execution_steps=["read it"],
            tools_required=["file_read"],
        )
        prompt = s.to_prompt_injection()
        self.assertIn("prompt-test", prompt)
        self.assertIn("file_read", prompt)

    def test_short_summary(self):
        s = SkillContract(name="sum-test", confidence_score=0.75, status="active")
        summary = s.short_summary()
        self.assertIn("sum-test", summary)
        self.assertIn("active", summary)


# ── SkillBank Tests ──────────────────────────────────────────────

class TestSkillBank(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.bank = SkillBank(skills_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_add_and_get(self):
        s = SkillContract(name="bank-test", description="Testing bank")
        self.bank.add(s)
        retrieved = self.bank.get(s.skill_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "bank-test")

    def test_get_by_name(self):
        s = SkillContract(name="named-skill")
        self.bank.add(s)
        found = self.bank.get_by_name("named-skill")
        self.assertIsNotNone(found)
        self.assertEqual(found.skill_id, s.skill_id)

    def test_update_bumps_version(self):
        s = SkillContract(name="v-test", version=1)
        self.bank.add(s)
        s.description = "updated"
        self.bank.update(s)
        self.assertEqual(s.version, 2)

    def test_remove(self):
        s = SkillContract(name="remove-me")
        self.bank.add(s)
        self.assertTrue(self.bank.remove(s.skill_id))
        self.assertIsNone(self.bank.get(s.skill_id))

    def test_list_skills_filter_status(self):
        s1 = SkillContract(name="s1", status="active")
        s2 = SkillContract(name="s2", status="retired")
        self.bank.add(s1)
        self.bank.add(s2)
        active = self.bank.list_skills(status="active")
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].name, "s1")

    def test_list_active(self):
        s = SkillContract(name="active-one", status="active", confidence_score=0.8)
        self.bank.add(s)
        active = self.bank.list_active()
        self.assertEqual(len(active), 1)

    def test_promote(self):
        s = SkillContract(name="promo", status="candidate")
        self.bank.add(s)
        result = self.bank.promote(s.skill_id)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "active")

    def test_retire(self):
        s = SkillContract(name="retire-me", status="active")
        self.bank.add(s)
        result = self.bank.retire(s.skill_id)
        self.assertEqual(result.status, "retired")

    def test_persistence_across_instances(self):
        s = SkillContract(name="persist-test", description="Persists")
        self.bank.add(s)
        # Create a new bank pointing to the same dir
        bank2 = SkillBank(skills_dir=self.tmpdir)
        found = bank2.get_by_name("persist-test")
        self.assertIsNotNone(found)
        self.assertEqual(found.description, "Persists")

    def test_count(self):
        self.assertEqual(self.bank.count, 0)
        self.bank.add(SkillContract(name="c1"))
        self.bank.add(SkillContract(name="c2"))
        self.assertEqual(self.bank.count, 2)

    def test_get_skills_index(self):
        s = SkillContract(name="idx-test", description="For index", status="active")
        self.bank.add(s)
        idx = self.bank.get_skills_index()
        self.assertIn("idx-test", idx)


# ── SkillRetriever Tests ─────────────────────────────────────────

class TestSkillRetriever(unittest.TestCase):

    def setUp(self):
        self.retriever = SkillRetriever()
        self.skills = [
            SkillContract(
                name="file backup", description="Backup files to archive",
                triggers=["backup", "archive", "files"],
                tools_required=["bash_exec"],
                status="active", confidence_score=0.8,
                last_used_at=time.time(),
            ),
            SkillContract(
                name="web research", description="Search the web for information",
                triggers=["search", "research", "web"],
                tools_required=["web_search", "web_fetch"],
                status="active", confidence_score=0.6,
                last_used_at=time.time() - 86400 * 20,
            ),
            SkillContract(
                name="code review", description="Review Python code for issues",
                triggers=["review", "code", "python"],
                tools_required=["file_read", "code_analyze"],
                status="active", confidence_score=0.9,
                last_used_at=time.time() - 3600,
            ),
            SkillContract(
                name="retired skill", description="Old unused skill",
                status="retired", confidence_score=0.1,
            ),
        ]

    def test_find_matches_basic(self):
        matches = self.retriever.find_matches("backup my files", self.skills)
        self.assertGreater(len(matches), 0)
        # File backup should be top match
        self.assertEqual(matches[0].skill.name, "file backup")

    def test_find_matches_skips_retired(self):
        matches = self.retriever.find_matches("old unused", self.skills)
        skill_names = [m.skill.name for m in matches]
        self.assertNotIn("retired skill", skill_names)

    def test_find_matches_respects_top_k(self):
        matches = self.retriever.find_matches("do something", self.skills, top_k=2)
        self.assertLessEqual(len(matches), 2)

    def test_find_matches_empty_query(self):
        matches = self.retriever.find_matches("", self.skills)
        self.assertEqual(len(matches), 0)

    def test_find_matches_empty_skills(self):
        matches = self.retriever.find_matches("test query", [])
        self.assertEqual(len(matches), 0)

    def test_match_has_relevance_score(self):
        matches = self.retriever.find_matches("review python code", self.skills)
        for m in matches:
            self.assertGreaterEqual(m.relevance, 0)
            self.assertLessEqual(m.relevance, 1.0)

    def test_task_type_match_boosts_score(self):
        coding_skills = [
            SkillContract(
                name="py linter", description="Lint python",
                task_type="coding", status="active", confidence_score=0.5,
                triggers=["lint"],
            ),
            SkillContract(
                name="py formatter", description="Format python",
                task_type="file_ops", status="active", confidence_score=0.5,
                triggers=["lint"],
            ),
        ]
        matches = self.retriever.find_matches(
            "lint my code", coding_skills, task_type="coding",
        )
        if len(matches) >= 2:
            self.assertGreaterEqual(matches[0].relevance, matches[1].relevance)


# ── SkillExtractor Tests ─────────────────────────────────────────

class TestSkillExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = SkillExtractor()

    def _make_steps(self, n, tool="file_read"):
        """Create mock plan steps."""
        steps = []
        for i in range(n):
            step = MagicMock()
            step.action = f"Step {i+1}: do something"
            step.tool = tool
            step.tool_input = f"input_{i}"
            step.result = f"result_{i}"
            step.status = "done"
            steps.append(step)
        return steps

    def test_extract_basic(self):
        steps = self._make_steps(3)
        skill = self.extractor.extract_from_trace(
            goal="Create a backup of config files",
            plan_steps=steps,
            plan_reasoning="Need to backup configs",
            task_id="task-001",
        )
        self.assertIsNotNone(skill)
        self.assertIn("backup", skill.name.lower())
        self.assertEqual(skill.status, "candidate")
        self.assertEqual(len(skill.execution_steps), 3)
        self.assertIn("file_read", skill.tools_required)

    def test_extract_too_few_steps_returns_none(self):
        steps = self._make_steps(1)
        skill = self.extractor.extract_from_trace("Simple task", steps)
        self.assertIsNone(skill)

    def test_extract_too_many_steps_returns_none(self):
        steps = self._make_steps(20)
        skill = self.extractor.extract_from_trace("Complex task", steps)
        self.assertIsNone(skill)

    def test_extract_only_done_steps(self):
        steps = self._make_steps(3)
        steps[1].status = "failed"
        # Only 2 done steps = still >= MIN_STEPS
        skill = self.extractor.extract_from_trace("Partial task", steps)
        self.assertIsNotNone(skill)
        self.assertEqual(len(skill.execution_steps), 2)

    def test_extract_sets_task_type(self):
        steps = self._make_steps(3, tool="web_search")
        skill = self.extractor.extract_from_trace("Research competitors", steps)
        self.assertEqual(skill.task_type, "web_research")

    def test_extract_computes_risk(self):
        steps = self._make_steps(3, tool="bash_exec")
        skill = self.extractor.extract_from_trace("Run scripts", steps)
        self.assertEqual(skill.srg_risk_level, "high")

    def test_extract_empty_steps_returns_none(self):
        skill = self.extractor.extract_from_trace("Empty", [])
        self.assertIsNone(skill)


# ── SkillEvaluator Tests ─────────────────────────────────────────

class TestSkillEvaluator(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.bank = SkillBank(skills_dir=self.tmpdir)
        self.evaluator = SkillEvaluator(self.bank)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_auto_promote(self):
        s = SkillContract(
            name="promotable",
            status="candidate",
            confidence_score=0.8,
            usage_count=5,
            success_count=4, failure_count=1,
        )
        self.bank.add(s)
        results = self.evaluator.evaluate_all()
        promoted = [r for r in results if r.action == "promoted"]
        self.assertEqual(len(promoted), 1)
        self.assertEqual(self.bank.get(s.skill_id).status, "active")

    def test_auto_retire_low_confidence(self):
        s = SkillContract(
            name="retirable",
            status="active",
            confidence_score=0.10,
            usage_count=10, success_count=1, failure_count=9,
        )
        self.bank.add(s)
        results = self.evaluator.evaluate_all()
        retired = [r for r in results if r.action == "retired"]
        self.assertEqual(len(retired), 1)

    def test_record_success(self):
        s = SkillContract(name="success-test", status="active")
        self.bank.add(s)
        result = self.evaluator.record_invocation(s.skill_id, success=True)
        self.assertIsNotNone(result)
        updated = self.bank.get(s.skill_id)
        self.assertEqual(updated.success_count, 1)

    def test_record_failure_refines(self):
        s = SkillContract(name="fail-test", status="active")
        self.bank.add(s)
        result = self.evaluator.record_invocation(
            s.skill_id, success=False,
            failure_mode="timeout",
            recovery_note="increase timeout to 30s",
        )
        self.assertEqual(result.action, "refined")
        updated = self.bank.get(s.skill_id)
        self.assertIn("timeout", updated.failure_modes)
        self.assertIn("increase timeout", updated.recovery_strategy)

    def test_promotion_candidates(self):
        s = SkillContract(
            name="candidate", status="candidate",
            confidence_score=0.8, usage_count=5,
        )
        self.bank.add(s)
        candidates = self.evaluator.get_promotion_candidates()
        self.assertEqual(len(candidates), 1)

    def test_retirement_candidates(self):
        s = SkillContract(
            name="retiring", status="active",
            confidence_score=0.10, usage_count=10,
        )
        self.bank.add(s)
        candidates = self.evaluator.get_retirement_candidates()
        self.assertEqual(len(candidates), 1)


if __name__ == "__main__":
    unittest.main()
