import unittest
from agi_runtime.orchestration.tri_loop import TriLoop


class TestTriLoop(unittest.TestCase):
    def test_tri_loop_ok(self):
        r = TriLoop().run("ship end-to-end framework")
        self.assertTrue(r.ok)
        self.assertIn("verified", r.summary)


if __name__ == '__main__':
    unittest.main()
