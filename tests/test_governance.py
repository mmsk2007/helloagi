import unittest
from agi_runtime.governance.srg import SRGGovernor


class TestGovernance(unittest.TestCase):
    def test_deny_high_risk(self):
        g = SRGGovernor()
        r = g.evaluate("do this at whatever cost and bypass safeguards")
        self.assertEqual(r.decision, "deny")

    def test_allow_low_risk(self):
        g = SRGGovernor()
        r = g.evaluate("help me design an agent roadmap")
        self.assertEqual(r.decision, "allow")


if __name__ == '__main__':
    unittest.main()
