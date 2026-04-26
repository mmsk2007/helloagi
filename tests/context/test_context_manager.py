import unittest

from agi_runtime.context.context_manager import ContextManager
from agi_runtime.context.context_segment import ContextSegment


class TestContextManager(unittest.TestCase):
    def test_build_supplement_respects_budget(self) -> None:
        cm = ContextManager({"managed": True, "max_budget_tokens": 200})
        seg = ContextSegment("memory", 5, "word " * 500, max_tokens=50, relevance_score=0.8)
        out = cm.build_supplement(query_hint="word", segments=[seg])
        self.assertIn("Structured context", out)
        self.assertLess(len(out), len(seg.content))


if __name__ == "__main__":
    unittest.main()
