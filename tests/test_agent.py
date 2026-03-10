import unittest
from agi_runtime.core.agent import HelloAGIAgent


class TestAgent(unittest.TestCase):
    def test_agent_response(self):
        a = HelloAGIAgent()
        r = a.think("help me build an agent")
        self.assertTrue(r.text)
        self.assertIn(r.decision, {"allow", "escalate", "deny"})


if __name__ == '__main__':
    unittest.main()
