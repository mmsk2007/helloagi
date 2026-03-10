from dataclasses import dataclass
from agi_runtime.scheduler.scheduler import AgentScheduler


@dataclass
class BackgroundExecutor:
    scheduler: AgentScheduler

    def tick(self) -> list[str]:
        return self.scheduler.due()
