import unittest

from agi_runtime.kernel.kernel import HelloAGIKernel


class TestKernel(unittest.TestCase):
    def test_boot_and_spawn(self):
        k = HelloAGIKernel.boot()
        k.spawn_agent("a1", "Alpha", "ship framework")
        self.assertIn("a1", k.registry.list_ids())
        self.assertTrue(k.capabilities.has("a1", "chat"))
        self.assertEqual(k.metering.get("agents.spawned"), 1)


if __name__ == '__main__':
    unittest.main()
