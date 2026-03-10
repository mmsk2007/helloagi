from dataclasses import dataclass

from agi_runtime.registry.agent_registry import AgentRegistry, AgentSpec
from agi_runtime.capabilities.manager import CapabilityManager
from agi_runtime.scheduler.scheduler import AgentScheduler
from agi_runtime.supervisor.supervisor import Supervisor
from agi_runtime.triggers.engine import TriggerEngine
from agi_runtime.metering.engine import MeteringEngine
from agi_runtime.background.executor import BackgroundExecutor
from agi_runtime.orchestration.orchestrator import Orchestrator
from agi_runtime.models.router import ModelRouter


@dataclass
class HelloAGIKernel:
    registry: AgentRegistry
    capabilities: CapabilityManager
    scheduler: AgentScheduler
    supervisor: Supervisor
    triggers: TriggerEngine
    metering: MeteringEngine
    background: BackgroundExecutor
    orchestrator: Orchestrator
    model_router: ModelRouter

    @classmethod
    def boot(cls) -> "HelloAGIKernel":
        scheduler = AgentScheduler()
        return cls(
            registry=AgentRegistry(),
            capabilities=CapabilityManager(),
            scheduler=scheduler,
            supervisor=Supervisor(),
            triggers=TriggerEngine(),
            metering=MeteringEngine(),
            background=BackgroundExecutor(scheduler=scheduler),
            orchestrator=Orchestrator(),
            model_router=ModelRouter(),
        )

    def spawn_agent(self, agent_id: str, name: str, goal: str):
        self.registry.register(AgentSpec(id=agent_id, name=name, goal=goal))
        self.capabilities.grant(agent_id, "chat")
        self.capabilities.grant(agent_id, "orchestrate")
        self.metering.add("agents.spawned", 1)
