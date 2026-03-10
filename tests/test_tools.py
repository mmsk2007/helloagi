import unittest
from agi_runtime.tools.registry import ToolRegistry


class TestTools(unittest.TestCase):
    def test_plan_tool(self):
        t = ToolRegistry()
        r = t.call("plan", "launch a product")
        self.assertTrue(r.ok)
        self.assertIn("1.", r.output)


if __name__ == '__main__':
    unittest.main()
