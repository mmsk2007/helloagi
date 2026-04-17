"""Tests for the Intelligence layer — Sentiment, Patterns, Context Compiler."""

from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path


class TestSentimentTracker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "mood.json")
        from agi_runtime.intelligence.sentiment import SentimentTracker
        self.tracker = SentimentTracker(path=self.path)

    def test_detect_positive(self):
        r = self.tracker.detect("This is amazing and I love it!")
        self.assertEqual(r.sentiment, "positive")
        self.assertGreater(r.score, 0)

    def test_detect_negative(self):
        r = self.tracker.detect("I'm frustrated and stuck on this bug")
        self.assertEqual(r.sentiment, "negative")
        self.assertLess(r.score, 0)

    def test_detect_neutral(self):
        r = self.tracker.detect("How do I configure the settings?")
        self.assertEqual(r.sentiment, "neutral")

    def test_record_saves(self):
        self.tracker.record("I'm happy!")
        self.assertTrue(Path(self.path).exists())
        data = json.loads(Path(self.path).read_text())
        self.assertEqual(len(data), 1)

    def test_current_mood(self):
        self.tracker.record("This is great!")
        self.tracker.record("Love it!")
        self.tracker.record("Amazing work!")
        self.assertEqual(self.tracker.get_current_mood(), "positive")

    def test_mood_guidance(self):
        # Record several negative messages
        for _ in range(5):
            self.tracker.record("I'm frustrated and stuck")
        guidance = self.tracker.get_mood_guidance()
        self.assertIn("support", guidance.lower())

    def test_summary(self):
        self.tracker.record("Great job!")
        summary = self.tracker.get_summary()
        self.assertIn("positive", summary)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestPatternDetector(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "patterns.json")
        from agi_runtime.intelligence.patterns import PatternDetector
        self.detector = PatternDetector(path=self.path)

    def test_record_interaction(self):
        self.detector.record_interaction("Write a Python script", ["python_exec"])
        self.assertEqual(len(self.detector.data["interactions"]), 1)

    def test_no_patterns_with_few_interactions(self):
        self.detector.record_interaction("Hello", [])
        patterns = self.detector.detect_patterns()
        self.assertEqual(len(patterns), 0)

    def test_detect_patterns_with_data(self):
        for i in range(10):
            self.detector.record_interaction(
                f"Write Python script number {i}",
                ["python_exec", "file_write"],
            )
        patterns = self.detector.detect_patterns()
        self.assertGreater(len(patterns), 0)

    def test_preferred_tools(self):
        for _ in range(10):
            self.detector.record_interaction("task", ["bash_exec", "file_read"])
        patterns = self.detector.detect_patterns()
        tool_pattern = [p for p in patterns if p.pattern_type == "preferred_tools"]
        self.assertEqual(len(tool_pattern), 1)
        self.assertIn("bash_exec", tool_pattern[0].description)

    def test_insights_string(self):
        for _ in range(10):
            self.detector.record_interaction("deploy application", ["bash_exec"])
        insights = self.detector.get_insights()
        self.assertIn("Patterns Detected", insights)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestContextCompiler(unittest.TestCase):
    def test_compile_basic(self):
        from agi_runtime.intelligence.context_compiler import ContextCompiler
        compiler = ContextCompiler()
        ctx = compiler.compile()
        self.assertIn(ctx.time_of_day, ["morning", "afternoon", "evening", "night"])
        self.assertTrue(ctx.os_name)
        self.assertTrue(ctx.python_version)

    def test_to_prompt(self):
        from agi_runtime.intelligence.context_compiler import ContextCompiler
        compiler = ContextCompiler()
        ctx = compiler.compile()
        prompt = ctx.to_prompt()
        self.assertIn("Current time", prompt)
        self.assertIn("Environment", prompt)

    def test_to_dict(self):
        from agi_runtime.intelligence.context_compiler import ContextCompiler
        compiler = ContextCompiler()
        ctx = compiler.compile()
        d = ctx.to_dict()
        self.assertIn("time_of_day", d)
        self.assertIn("os_name", d)


if __name__ == "__main__":
    unittest.main()
