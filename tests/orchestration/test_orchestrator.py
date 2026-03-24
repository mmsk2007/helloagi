import tempfile
import unittest

from agi_runtime.orchestration.event_bus import EventBus
from agi_runtime.orchestration.orchestrator import Orchestrator, OrchestratorConfig
from agi_runtime.state.store import StateStore
from agi_runtime.workflows.graph import WorkflowGraph, WorkflowNode


class TestOrchestrator(unittest.TestCase):
    def test_run_once_executes_ready(self):
        g = WorkflowGraph()
        g.add_node(WorkflowNode(id="a", title="A"))
        g.add_node(WorkflowNode(id="b", title="B", deps=["a"]))

        done = set()
        orch = Orchestrator()
        ex = orch.run_once(g, done)
        self.assertIn("a", ex)
        self.assertIn("a", done)

    def test_run_once_records_deferred_backlog_and_emits_event(self):
        g = WorkflowGraph()
        g.add_node(WorkflowNode(id="a", title="A"))
        g.add_node(WorkflowNode(id="b", title="B"))
        g.add_node(WorkflowNode(id="c", title="C", deps=["a"]))

        captured: list[dict] = []
        bus = EventBus()
        bus.on("task.deferred", lambda ev: captured.append(ev))

        with tempfile.TemporaryDirectory() as td:
            orch = Orchestrator(
                OrchestratorConfig(max_parallel=1),
                bus=bus,
                store=StateStore(path=f"{td}/runtime_state.json"),
            )

            done = set()
            ex = orch.run_once(g, done)
            state = orch.store.load()

        self.assertEqual(ex, ["a"])
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].kind, "task.deferred")
        self.assertEqual(captured[0].payload["node_id"], "b")
        self.assertEqual(captured[0].payload["reason"], "max_parallel_reached")
        self.assertEqual(
            state["metrics"]["last_orchestrator_run"],
            {
                "ready": 2,
                "executed": 1,
                "deferred": 1,
                "remaining": 2,
                "max_parallel": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
