from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TERMINAL_NODE_STATUSES = {"completed", "failed", "escalated", "canceled"}


@dataclass
class WorkflowNode:
    id: str
    title: str
    deps: list[str] = field(default_factory=list)
    kind: str = "task"  # task | tool | delegation | verification
    prompt: str = ""
    tool: str | None = None
    tool_input: dict[str, Any] | None = None
    success_criteria: str = ""
    retry_limit: int = 0
    timeout_s: int | None = None
    escalate_on_failure: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowNode":
        return cls(
            id=data["id"],
            title=data["title"],
            deps=list(data.get("deps", [])),
            kind=data.get("kind", "task"),
            prompt=data.get("prompt", ""),
            tool=data.get("tool"),
            tool_input=data.get("tool_input"),
            success_criteria=data.get("success_criteria", ""),
            retry_limit=int(data.get("retry_limit", 0)),
            timeout_s=data.get("timeout_s"),
            escalate_on_failure=bool(data.get("escalate_on_failure", False)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class WorkflowGraph:
    nodes: dict[str, WorkflowNode] = field(default_factory=dict)

    def add_node(self, node: WorkflowNode):
        self.nodes[node.id] = node

    def get(self, node_id: str) -> WorkflowNode:
        return self.nodes[node_id]

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()}}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowGraph":
        graph = cls()
        for node_id, node_data in data.get("nodes", {}).items():
            graph.add_node(WorkflowNode.from_dict(node_data))
        return graph

    def ready_nodes(self, states: dict[str, dict[str, Any]] = None, done: set[str] = None) -> list[WorkflowNode]:
        if states is None:
            done = done or set()
            states = {node_id: {"status": "completed" if node_id in done else "pending"} for node_id in self.nodes}
        ready: list[WorkflowNode] = []
        for node in self.nodes.values():
            node_state = states.get(node.id, {})
            status = node_state.get("status", "pending")
            if status != "pending":
                continue
            if all(states.get(dep, {}).get("status") == "completed" for dep in node.deps):
                ready.append(node)
        return ready

    def blocked_nodes(self, states: dict[str, dict[str, Any]]) -> list[WorkflowNode]:
        blocked: list[WorkflowNode] = []
        for node in self.nodes.values():
            node_state = states.get(node.id, {})
            status = node_state.get("status", "pending")
            if status != "pending":
                continue
            dep_statuses = [states.get(dep, {}).get("status", "pending") for dep in node.deps]
            if any(dep_status in TERMINAL_NODE_STATUSES - {"completed"} for dep_status in dep_statuses):
                blocked.append(node)
        return blocked

    def is_complete(self, states: dict[str, dict[str, Any]]) -> bool:
        return all(states.get(node_id, {}).get("status") in TERMINAL_NODE_STATUSES for node_id in self.nodes)
