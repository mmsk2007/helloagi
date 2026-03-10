import unittest
from agi_runtime.workflows.graph import WorkflowGraph, WorkflowNode
from agi_runtime.orchestration.orchestrator import Orchestrator


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


if __name__ == "__main__":
    unittest.main()
