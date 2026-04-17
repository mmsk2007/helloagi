"""Tests for the skill system."""

import unittest
import shutil
from pathlib import Path

from agi_runtime.skills.manager import SkillManager


class TestSkillManager(unittest.TestCase):
    def setUp(self):
        self.sm = SkillManager(skills_dir="test_skills_tmp")

    def tearDown(self):
        shutil.rmtree("test_skills_tmp", ignore_errors=True)

    def test_create_skill(self):
        self.sm.create_skill(
            name="test-skill",
            description="A test skill",
            triggers=["test", "check"],
            tools=["python_exec"],
            steps=["Run test", "Verify output"],
        )
        skills = self.sm.list_skills()
        assert len(skills) == 1
        assert skills[0].name == "test-skill"
        assert skills[0].description == "A test skill"
        assert "test" in skills[0].triggers
        assert "python_exec" in skills[0].tools

    def test_find_matching_skill(self):
        self.sm.create_skill(
            name="deploy-app",
            description="Deploy an application",
            triggers=["deploy", "release", "ship"],
            tools=["bash_exec"],
            steps=["Build", "Deploy"],
        )
        match = self.sm.find_matching_skill("please deploy my app")
        assert match is not None
        assert match.name == "deploy-app"

    def test_no_match(self):
        self.sm.create_skill(
            name="deploy-app",
            description="Deploy",
            triggers=["deploy"],
            tools=["bash_exec"],
            steps=["Deploy"],
        )
        match = self.sm.find_matching_skill("what is the weather")
        assert match is None

    def test_delete_skill(self):
        self.sm.create_skill(
            name="temp",
            description="Temporary",
            triggers=["temp"],
            tools=[],
            steps=["Do thing"],
        )
        assert len(self.sm.list_skills()) == 1
        self.sm.delete_skill("temp")
        assert len(self.sm.list_skills()) == 0

    def test_get_skills_index(self):
        self.sm.create_skill(
            name="s1",
            description="Skill one",
            triggers=["one"],
            tools=["t1"],
            steps=["Step 1"],
        )
        idx = self.sm.get_skills_index()
        assert "s1" in idx
        assert "Skill one" in idx

    def test_invoke_count(self):
        self.sm.create_skill(
            name="counted",
            description="Counted",
            triggers=["count"],
            tools=[],
            steps=["Step"],
        )
        self.sm.increment_invoke_count("counted")
        self.sm.increment_invoke_count("counted")
        skills = self.sm.list_skills()
        assert skills[0].invoke_count == 2


if __name__ == "__main__":
    unittest.main()
