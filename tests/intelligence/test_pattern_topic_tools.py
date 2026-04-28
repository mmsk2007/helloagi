"""PatternDetector — task-scoped tool hint tests.

``get_tools_for_topic`` powers the ``<task-pattern-hint>`` block injected
into the agent's system prompt. The contract:
- only past interactions whose topic words overlap with the query are counted
- min_uses gates the noise floor
- output is sorted most-used-first, length capped to top_n
"""

import json
import tempfile
import unittest
from pathlib import Path

from agi_runtime.intelligence.patterns import PatternDetector


def _seed(detector: PatternDetector, interactions: list) -> None:
    detector.data["interactions"] = interactions
    detector._save()


class TestGetToolsForTopic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "patterns.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_topic_overlap_returns_relevant_tools(self):
        d = PatternDetector(self.path)
        _seed(d, [
            {"ts": 1, "hour": 9, "tools": ["browser_navigate", "browser_click"],
             "topic_words": ["instagram", "followers", "profile"]},
            {"ts": 2, "hour": 9, "tools": ["browser_navigate"],
             "topic_words": ["instagram", "followers"]},
            {"ts": 3, "hour": 9, "tools": ["bash_exec"],
             "topic_words": ["python", "script"]},
        ])
        # "How many followers do we have on instagram?" — should pick up the
        # two browser-based tasks, not the bash one.
        tools = d.get_tools_for_topic(
            "how many followers do we have on instagram",
            top_n=3,
            min_uses=2,
        )
        names = [t for t, _ in tools]
        self.assertIn("browser_navigate", names)
        self.assertNotIn("bash_exec", names)

    def test_min_uses_filters_noise(self):
        d = PatternDetector(self.path)
        _seed(d, [
            {"ts": 1, "hour": 9, "tools": ["browser_navigate"],
             "topic_words": ["instagram"]},
        ])
        tools = d.get_tools_for_topic("instagram followers", min_uses=2)
        self.assertEqual(tools, [])

    def test_no_overlap_returns_empty(self):
        d = PatternDetector(self.path)
        _seed(d, [
            {"ts": 1, "hour": 9, "tools": ["browser_navigate", "browser_navigate"],
             "topic_words": ["coffee", "espresso"]},
        ])
        tools = d.get_tools_for_topic("python script for parsing logs")
        self.assertEqual(tools, [])

    def test_short_query_returns_empty(self):
        d = PatternDetector(self.path)
        _seed(d, [
            {"ts": 1, "hour": 9, "tools": ["x"], "topic_words": ["instagram"]},
        ])
        # "do x" — no words long enough to extract; nothing to match against.
        self.assertEqual(d.get_tools_for_topic("do x"), [])

    def test_top_n_caps_result(self):
        d = PatternDetector(self.path)
        _seed(d, [
            {"ts": i, "hour": 9, "tools": [f"tool_{i % 5}", f"tool_{i % 5}"],
             "topic_words": ["instagram"]}
            for i in range(20)
        ])
        tools = d.get_tools_for_topic("instagram followers", top_n=2, min_uses=2)
        self.assertEqual(len(tools), 2)


if __name__ == "__main__":
    unittest.main()
