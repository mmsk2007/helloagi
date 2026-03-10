import unittest
from agi_runtime.latency.ale import ALEngine


class TestALE(unittest.TestCase):
    def test_ale_cache_roundtrip(self):
        a = ALEngine()
        q = "help me build an agent"
        self.assertIsNone(a.get(q))
        a.put(q, "cached")
        self.assertEqual(a.get(q), "cached")


if __name__ == '__main__':
    unittest.main()
