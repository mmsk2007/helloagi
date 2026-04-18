import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agi_runtime.orchestration.orchestrator import Orchestrator
from agi_runtime.state.store import StateStore
from agi_runtime.workflows.graph import WorkflowGraph, WorkflowNode


class TestRunsRuntime(unittest.TestCase):
    def test_cancel_run_marks_pending_nodes_canceled(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(str(Path(tmp) / "runtime_state.json"))
            orch = Orchestrator(store=store)
            graph = WorkflowGraph()
            graph.add_node(WorkflowNode(id="observe", title="Observe"))
            graph.add_node(WorkflowNode(id="plan", title="Plan", deps=["observe"]))
            run_id = orch.start_run(graph, title="cancel me")
            workflow = orch.cancel_run(run_id)
            self.assertEqual(workflow["status"], "canceled")
            self.assertEqual(workflow["nodes"]["observe"]["status"], "canceled")
            self.assertEqual(workflow["nodes"]["plan"]["status"], "canceled")

    def test_summarize_run_returns_node_statuses(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(str(Path(tmp) / "runtime_state.json"))
            orch = Orchestrator(store=store)
            graph = WorkflowGraph()
            graph.add_node(WorkflowNode(id="observe", title="Observe", prompt="done"))
            workflow = orch.run_until_complete(graph, title="summary")
            summary = orch.summarize_run(workflow["id"])
            self.assertEqual(summary["status"], "completed")
            self.assertIn("observe", summary["nodes"])

    def test_export_run_redacts_sensitive_output(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(str(Path(tmp) / "runtime_state.json"))
            orch = Orchestrator(store=store)
            graph = WorkflowGraph()
            graph.add_node(WorkflowNode(id="observe", title="Observe", prompt="token sk-secretvalue1234567890"))
            workflow = orch.run_until_complete(graph, title="export")
            exported = orch.export_run(workflow["id"])
            self.assertIn("observe", exported["nodes"])
            self.assertIn("[redacted]", exported["nodes"]["observe"]["last_output"])
