from dataclasses import dataclass
from agi_runtime.workflows.graph import WorkflowGraph
from agi_runtime.orchestration.event_bus import EventBus
from agi_runtime.state.store import StateStore


@dataclass
class OrchestratorConfig:
    max_parallel: int = 3


class Orchestrator:
    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        *,
        bus: EventBus | None = None,
        store: StateStore | None = None,
    ):
        self.config = config or OrchestratorConfig()
        self.bus = bus or EventBus()
        self.store = store or StateStore()

    def run_once(self, graph: WorkflowGraph, done: set[str]) -> list[str]:
        ready = graph.ready_nodes(done)
        picked = ready[: self.config.max_parallel]
        deferred = ready[self.config.max_parallel :]
        executed = []

        for n in deferred:
            self.bus.emit(
                "task.deferred",
                {
                    "node_id": n.id,
                    "title": n.title,
                    "reason": "max_parallel_reached",
                },
            )

        for n in picked:
            self.bus.emit("task.started", {"node_id": n.id, "title": n.title})
            # placeholder execution path
            done.add(n.id)
            executed.append(n.id)
            self.bus.emit("task.completed", {"node_id": n.id})

        state = self.store.load()
        metrics = state.setdefault("metrics", {})
        metrics.setdefault("executed", 0)
        metrics["executed"] += len(executed)
        metrics["last_orchestrator_run"] = {
            "ready": len(ready),
            "executed": len(executed),
            "deferred": len(deferred),
            "remaining": max(0, len(graph.nodes) - len(done)),
            "max_parallel": self.config.max_parallel,
        }
        self.store.save(state)
        return executed
