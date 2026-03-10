from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class WorkflowNode:
    id: str
    title: str
    deps: List[str] = field(default_factory=list)


@dataclass
class WorkflowGraph:
    nodes: Dict[str, WorkflowNode] = field(default_factory=dict)

    def add_node(self, node: WorkflowNode):
        self.nodes[node.id] = node

    def ready_nodes(self, done: set[str]) -> List[WorkflowNode]:
        out = []
        for n in self.nodes.values():
            if n.id in done:
                continue
            if all(d in done for d in n.deps):
                out.append(n)
        return out
