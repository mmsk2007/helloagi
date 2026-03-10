from dataclasses import dataclass
from agi_runtime.workflows.graph import WorkflowGraph
from agi_runtime.orchestration.event_bus import EventBus
from agi_runtime.state.store import StateStore


@dataclass
class OrchestratorConfig:
    max_parallel: int = 3


class Orchestrator:
    def __init__(self, config: OrchestratorConfig | None = None):
        self.config = config or OrchestratorConfig()
        self.bus = EventBus()
        self.store = StateStore()

    def run_once(self, graph: WorkflowGraph, done: set[str]) -> list[str]:
        ready = graph.ready_nodes(done)
        picked = ready[: self.config.max_parallel]
        executed = []
        for n in picked:
            self.bus.emit("task.started", {"node_id": n.id, "title": n.title})
            # placeholder execution path
            done.add(n.id)
            executed.append(n.id)
            self.bus.emit("task.completed", {"node_id": n.id})
        state = self.store.load()
        state.setdefault("metrics", {}).setdefault("executed", 0)
        state["metrics"]["executed"] += len(executed)
        self.store.save(state)
        return executed
