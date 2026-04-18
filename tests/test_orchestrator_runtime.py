import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agi_runtime.orchestration.orchestrator import Orchestrator
from agi_runtime.state.store import StateStore
from agi_runtime.workflows.graph import WorkflowGraph, WorkflowNode


class TestOrchestratorRuntime(unittest.TestCase):
    def test_run_until_complete_persists_completed_nodes(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(str(Path(tmp) / "runtime_state.json"))
            orch = Orchestrator(store=store)
            graph = WorkflowGraph()
            graph.add_node(WorkflowNode(id="observe", title="Observe", prompt="Observed"))
            graph.add_node(WorkflowNode(id="plan", title="Plan", deps=["observe"], prompt="Planned"))
            workflow = orch.run_until_complete(graph, title="test workflow")
            self.assertEqual(workflow["status"], "completed")
            self.assertEqual(workflow["nodes"]["observe"]["status"], "completed")
            self.assertEqual(workflow["nodes"]["plan"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
