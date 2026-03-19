import unittest

from agi_runtime.scheduler.scheduler import AgentScheduler


class TestAgentScheduler(unittest.TestCase):
    def test_schedule_dedupes_same_agent_and_tracks_reason(self):
        scheduler = AgentScheduler()

        first = scheduler.schedule_in("a1", 30, reason="heartbeat")
        second = scheduler.schedule_in("a1", 10, reason="retry")

        self.assertGreater(first, second)
        pending = scheduler.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["agent_id"], "a1")
        self.assertEqual(pending[0]["reason"], "retry")

    def test_due_uses_order_and_supports_injected_now(self):
        scheduler = AgentScheduler()
        scheduler.schedule_in("later", 20)
        scheduler.schedule_in("sooner", 5)

        ready = scheduler.due(now=scheduler.pending()[0]["run_at"] + 0.1)

        self.assertEqual(ready, ["sooner"])
        self.assertEqual([item["agent_id"] for item in scheduler.pending()], ["later"])

    def test_cancel_and_next_due_in(self):
        scheduler = AgentScheduler()
        scheduler.schedule_in("a1", 10)
        scheduler.schedule_in("a2", 20)

        removed = scheduler.cancel("a2")

        self.assertEqual(removed, 1)
        self.assertEqual([item["agent_id"] for item in scheduler.pending()], ["a1"])
        self.assertAlmostEqual(scheduler.next_due_in(now=scheduler.pending()[0]["created_at"]), 10, delta=0.5)


if __name__ == "__main__":
    unittest.main()
