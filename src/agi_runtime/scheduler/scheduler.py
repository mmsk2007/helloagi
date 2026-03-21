from collections import Counter
from dataclasses import asdict, dataclass, field
import time


@dataclass
class ScheduleItem:
    agent_id: str
    run_at: float
    reason: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class AgentScheduler:
    queue: list[ScheduleItem] = field(default_factory=list)

    def schedule_in(self, agent_id: str, seconds: float, *, reason: str = "", dedupe: bool = True) -> float:
        run_at = time.time() + seconds
        if dedupe:
            # Keep only the newest scheduled run per agent so autonomous loops do not pile up.
            self.queue = [item for item in self.queue if item.agent_id != agent_id]
        self.queue.append(ScheduleItem(agent_id=agent_id, run_at=run_at, reason=reason))
        self.queue.sort(key=lambda item: item.run_at)
        return run_at

    def cancel(self, agent_id: str) -> int:
        before = len(self.queue)
        self.queue = [item for item in self.queue if item.agent_id != agent_id]
        return before - len(self.queue)

    def due(self, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        ready = [x.agent_id for x in self.queue if x.run_at <= now]
        self.queue = [x for x in self.queue if x.run_at > now]
        return ready

    def pending(self) -> list[dict]:
        return [asdict(item) for item in sorted(self.queue, key=lambda item: item.run_at)]

    def next_due_in(self, now: float | None = None) -> float | None:
        if not self.queue:
            return None
        now = time.time() if now is None else now
        return max(0.0, self.queue[0].run_at - now)

    def queue_summary(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        pending = sorted(self.queue, key=lambda item: item.run_at)
        if not pending:
            return {
                "total": 0,
                "next_due_in": None,
                "next_run_at": None,
                "agents": {},
                "reasons": {},
            }

        agent_counts = Counter(item.agent_id for item in pending)
        reason_counts = Counter(item.reason or "unspecified" for item in pending)
        next_item = pending[0]
        return {
            "total": len(pending),
            "next_due_in": max(0.0, next_item.run_at - now),
            "next_run_at": next_item.run_at,
            "agents": dict(sorted(agent_counts.items())),
            "reasons": dict(sorted(reason_counts.items())),
        }
