import unittest
from agi_runtime.workflows.graph import WorkflowGraph, WorkflowNode


class TestGraph(unittest.TestCase):
    def test_ready_nodes(self):
        g = WorkflowGraph()
        g.add_node(WorkflowNode(id="a", title="A"))
        g.add_node(WorkflowNode(id="b", title="B", deps=["a"]))
        ready = g.ready_nodes(done=set())
        self.assertEqual([n.id for n in ready], ["a"])


if __name__ == "__main__":
    unittest.main()
