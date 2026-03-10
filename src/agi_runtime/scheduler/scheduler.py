from dataclasses import dataclass, field
import time


@dataclass
class ScheduleItem:
    agent_id: str
    run_at: float


@dataclass
class AgentScheduler:
    queue: list[ScheduleItem] = field(default_factory=list)

    def schedule_in(self, agent_id: str, seconds: float):
        self.queue.append(ScheduleItem(agent_id=agent_id, run_at=time.time() + seconds))

    def due(self) -> list[str]:
        now = time.time()
        ready = [x.agent_id for x in self.queue if x.run_at <= now]
        self.queue = [x for x in self.queue if x.run_at > now]
        return ready
