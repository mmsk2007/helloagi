from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import time
import uuid
from typing import Any

from agi_runtime.executor.executor import Executor
from agi_runtime.orchestration.event_bus import EventBus
from agi_runtime.state.store import StateStore
from agi_runtime.workflows.graph import TERMINAL_NODE_STATUSES, WorkflowGraph, WorkflowNode


@dataclass
class OrchestratorConfig:
    max_parallel: int = 3
    retry_backoff_s: float = 0.0


@dataclass
class NodeExecutionResult:
    node_id: str
    status: str
    output: str
    attempts: int
    escalated: bool = False


class Orchestrator:
    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        *,
        executor: Executor | None = None,
        bus: EventBus | None = None,
        store: StateStore | None = None,
    ):
        self.config = config or OrchestratorConfig()
        self.executor = executor or Executor()
        self.bus = bus or EventBus()
        self.store = store or StateStore()

    def start_run(self, graph: WorkflowGraph, title: str = "") -> str:
        run_id = str(uuid.uuid4())
        state = self.store.load()
        workflows = state.setdefault("workflows", {})
        workflows[run_id] = {
            "id": run_id,
            "title": title or "workflow run",
            "created_at": time.time(),
            "updated_at": time.time(),
            "status": "running",
            "graph": graph.to_dict(),
            "nodes": {
                node_id: {
                    "status": "pending",
                    "attempts": 0,
                    "last_output": "",
                    "started_at": None,
                    "finished_at": None,
                    "kind": node.kind,
                    "title": node.title,
                }
                for node_id, node in graph.nodes.items()
            },
            "history": [],
            "metrics": {
                "executed": 0,
                "completed": 0,
                "failed": 0,
                "escalated": 0,
                "deferred": 0,
            },
        }
        self.store.save(state)
        return run_id

    def resume_run(self, run_id: str) -> dict[str, Any]:
        state = self.store.load()
        workflow = state.get("workflows", {}).get(run_id)
        if not workflow:
            raise KeyError(f"Unknown workflow run: {run_id}")
        return workflow

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.resume_run(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        state = self.store.load()
        workflows = state.get("workflows", {})
        return sorted(workflows.values(), key=lambda item: item.get("created_at", 0), reverse=True)

    def run_until_complete(self, graph: WorkflowGraph, title: str = "") -> dict[str, Any]:
        run_id = self.start_run(graph, title=title)
        return self.continue_run(run_id)

    def continue_run(self, run_id: str) -> dict[str, Any]:
        while True:
            executed = self.run_once(run_id)
            workflow = self.resume_run(run_id)
            if workflow["status"] in {"completed", "failed", "escalated", "canceled"}:
                return workflow
            if not executed:
                return workflow

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        state = self.store.load()
        workflow = state.get("workflows", {}).get(run_id)
        if not workflow:
            raise KeyError(f"Unknown workflow run: {run_id}")
        for node_state in workflow.get("nodes", {}).values():
            if node_state.get("status") in {"pending", "ready", "running"}:
                node_state["status"] = "canceled"
                node_state["finished_at"] = time.time()
                node_state["last_output"] = "Canceled by operator."
        workflow["status"] = "canceled"
        workflow["updated_at"] = time.time()
        self._append_history(workflow, "task.canceled", {"reason": "operator_requested"})
        state["workflows"][run_id] = workflow
        self.store.save(state)
        return workflow

    def summarize_run(self, run_id: str) -> dict[str, Any]:
        workflow = self.resume_run(run_id)
        node_statuses = {
            node_id: {
                "status": data.get("status"),
                "attempts": data.get("attempts"),
                "title": data.get("title"),
                "kind": data.get("kind"),
                "last_output": data.get("last_output", "")[:200],
            }
            for node_id, data in workflow.get("nodes", {}).items()
        }
        return {
            "id": workflow["id"],
            "title": workflow.get("title", ""),
            "status": workflow.get("status"),
            "created_at": workflow.get("created_at"),
            "updated_at": workflow.get("updated_at"),
            "metrics": workflow.get("metrics", {}),
            "nodes": node_statuses,
            "history": workflow.get("history", []),
        }

    def export_run(self, run_id: str) -> dict[str, Any]:
        workflow = self.resume_run(run_id)
        nodes = {}
        for node_id, data in workflow.get("nodes", {}).items():
            nodes[node_id] = {
                "status": data.get("status"),
                "attempts": data.get("attempts"),
                "title": data.get("title"),
                "kind": data.get("kind"),
                "last_output": self._sanitize_output(data.get("last_output", "")),
            }
        history = []
        for item in workflow.get("history", []):
            payload = dict(item.get("payload", {}))
            if "output_preview" in payload:
                payload["output_preview"] = self._sanitize_output(str(payload.get("output_preview", "")))
            history.append(
                {
                    "ts": item.get("ts"),
                    "kind": item.get("kind"),
                    "payload": payload,
                }
            )
        return {
            "id": workflow["id"],
            "title": workflow.get("title", ""),
            "status": workflow.get("status"),
            "created_at": workflow.get("created_at"),
            "updated_at": workflow.get("updated_at"),
            "metrics": workflow.get("metrics", {}),
            "nodes": nodes,
            "history": history,
        }

    def run_once(self, run_id_or_graph, done: set[str] = None) -> list[str]:
        if isinstance(run_id_or_graph, WorkflowGraph):
            graph = run_id_or_graph
            if done is None:
                done = set()
            ready = graph.ready_nodes(done=done)
            picked = ready[: self.config.max_parallel]
            deferred = ready[self.config.max_parallel :]
            executed_ids: list[str] = []
            for node in deferred:
                self.bus.emit("task.deferred", {"node_id": node.id, "title": node.title, "reason": "max_parallel_reached"})
            for node in picked:
                done.add(node.id)
                executed_ids.append(node.id)
                self.bus.emit("task.started", {"node_id": node.id, "title": node.title, "kind": node.kind})
                self.bus.emit("task.completed", {"node_id": node.id, "title": node.title})
            state = self.store.load()
            metrics = state.setdefault("metrics", {})
            metrics.setdefault("executed", 0)
            metrics["executed"] += len(executed_ids)
            metrics["last_orchestrator_run"] = {
                "ready": len(ready),
                "executed": len(executed_ids),
                "deferred": len(deferred),
                "remaining": max(0, len(graph.nodes) - len(done)),
                "max_parallel": self.config.max_parallel,
            }
            self.store.save(state)
            return executed_ids

        run_id = run_id_or_graph
        state = self.store.load()
        workflow = state.get("workflows", {}).get(run_id)
        if not workflow:
            raise KeyError(f"Unknown workflow run: {run_id}")

        graph = WorkflowGraph.from_dict(workflow["graph"])
        nodes_state = workflow["nodes"]
        ready = graph.ready_nodes(nodes_state)
        picked = ready[: self.config.max_parallel]
        deferred = ready[self.config.max_parallel :]
        executed_ids: list[str] = []

        for node in deferred:
            workflow["metrics"]["deferred"] += 1
            self._append_history(workflow, "task.deferred", {"node_id": node.id, "reason": "max_parallel_reached"})
            self.bus.emit("task.deferred", {"node_id": node.id, "title": node.title, "reason": "max_parallel_reached"})

        for node in picked:
            result = self._execute_node(node, nodes_state[node.id])
            executed_ids.append(node.id)
            workflow["metrics"]["executed"] += 1
            if result.status == "completed":
                workflow["metrics"]["completed"] += 1
            elif result.status == "failed":
                workflow["metrics"]["failed"] += 1
            elif result.status == "escalated":
                workflow["metrics"]["escalated"] += 1
            self._append_history(
                workflow,
                f"task.{result.status}",
                {
                    "node_id": node.id,
                    "attempts": result.attempts,
                    "output_preview": result.output[:200],
                },
            )

        self._mark_blocked_nodes(graph, workflow)
        self._finalize_workflow_status(graph, workflow)
        workflow["updated_at"] = time.time()
        state["workflows"][run_id] = workflow
        self.store.save(state)
        return executed_ids

    def _execute_node(self, node: WorkflowNode, node_state: dict[str, Any]) -> NodeExecutionResult:
        node_state["status"] = "running"
        node_state["started_at"] = time.time()
        node_state["attempts"] = int(node_state.get("attempts", 0)) + 1
        self.bus.emit("task.started", {"node_id": node.id, "title": node.title, "kind": node.kind})

        if node.kind in {"tool", "delegation"} and node.tool:
            plan_like = [
                {
                    "id": 1,
                    "action": node.title,
                    "tool": node.tool,
                    "tool_input": node.tool_input or {},
                }
            ]
            exec_result = self.executor.run(
                self._build_single_step_plan(node.title, node.tool, node.tool_input or {})
            )
            step_result = exec_result.outputs[0] if exec_result.outputs else None
            ok = bool(step_result and step_result.ok)
            output = step_result.output if step_result else f"No output for node {node.id}"
        else:
            ok = True
            output = node.prompt or node.title

        final_status = "completed" if ok else "failed"
        if not ok and node_state["attempts"] <= node.retry_limit:
            final_status = "pending"
        elif not ok and node.escalate_on_failure:
            final_status = "escalated"

        node_state["status"] = final_status
        node_state["last_output"] = output
        node_state["finished_at"] = time.time() if final_status in TERMINAL_NODE_STATUSES else None

        if final_status == "pending":
            self.bus.emit("task.retry_scheduled", {"node_id": node.id, "attempts": node_state["attempts"]})
            return NodeExecutionResult(node.id, final_status, output, node_state["attempts"])

        event_name = "task.completed" if final_status == "completed" else "task.failed"
        if final_status == "escalated":
            event_name = "task.escalated"
        self.bus.emit(event_name, {"node_id": node.id, "title": node.title, "output_preview": output[:120]})
        return NodeExecutionResult(node.id, final_status, output, node_state["attempts"], escalated=final_status == "escalated")

    def _mark_blocked_nodes(self, graph: WorkflowGraph, workflow: dict[str, Any]):
        for node in graph.blocked_nodes(workflow["nodes"]):
            node_state = workflow["nodes"][node.id]
            if node_state["status"] != "pending":
                continue
            node_state["status"] = "canceled"
            node_state["last_output"] = "Canceled because a dependency failed or escalated."
            node_state["finished_at"] = time.time()
            self._append_history(workflow, "task.canceled", {"node_id": node.id})
            self.bus.emit("task.canceled", {"node_id": node.id, "title": node.title})

    def _finalize_workflow_status(self, graph: WorkflowGraph, workflow: dict[str, Any]):
        node_states = workflow["nodes"]
        statuses = {node_id: data.get("status", "pending") for node_id, data in node_states.items()}
        if all(status == "completed" for status in statuses.values()):
            workflow["status"] = "completed"
            return
        if any(status == "escalated" for status in statuses.values()):
            workflow["status"] = "escalated"
            return
        if graph.is_complete(node_states):
            workflow["status"] = "failed"
            return
        workflow["status"] = "running"

    def _append_history(self, workflow: dict[str, Any], kind: str, payload: dict[str, Any]):
        workflow.setdefault("history", []).append({"ts": time.time(), "kind": kind, "payload": payload})

    def _build_single_step_plan(self, title: str, tool: str, tool_input: dict[str, Any]):
        from agi_runtime.planner.planner import Plan, PlanStep

        return Plan(
            goal=title,
            steps=[
                PlanStep(
                    id=1,
                    action=title,
                    tool=tool,
                    tool_input=tool_input,
                    success_criteria=title,
                )
            ],
            reasoning="single-node workflow execution",
        )

    @staticmethod
    def _sanitize_output(text: str, limit: int = 200) -> str:
        if not text:
            return ""
        redacted = re.sub(r"(?i)\b(sk-[a-z0-9_-]{8,}|[a-z0-9_-]{20,}\.[a-z0-9._-]{6,}\.[a-z0-9._-]{6,})\b", "[redacted]", text)
        return redacted[:limit]
