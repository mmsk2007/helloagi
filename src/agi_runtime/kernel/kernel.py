"""HelloAGI Kernel — Composes all subsystems into a unified runtime.

The kernel bootstraps and wires together:
- Agent registry + capability manager
- Tool registry with all builtin tools
- SRG governance
- Scheduler + supervisor
- Skill manager
- Orchestrator + event bus
- Model router
"""

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
from agi_runtime.tools.registry import ToolRegistry, discover_builtin_tools
from agi_runtime.governance.srg import SRGGovernor
from agi_runtime.skills.manager import SkillManager


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
    tool_registry: ToolRegistry
    governor: SRGGovernor
    skill_manager: SkillManager

    @classmethod
    def boot(cls, policy_pack: str = "safe-default") -> "HelloAGIKernel":
        """Bootstrap the full HelloAGI runtime."""
        # Initialize tool registry and discover all builtin tools
        tool_registry = ToolRegistry.get_instance()
        discover_builtin_tools()

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
            tool_registry=tool_registry,
            governor=SRGGovernor(policy_pack=policy_pack),
            skill_manager=SkillManager(),
        )

    def spawn_agent(self, agent_id: str, name: str, goal: str):
        self.registry.register(AgentSpec(id=agent_id, name=name, goal=goal))
        self.capabilities.grant(agent_id, "chat")
        self.capabilities.grant(agent_id, "orchestrate")
        self.capabilities.grant(agent_id, "tools")
        self.metering.add("agents.spawned", 1)

    @property
    def tools_count(self) -> int:
        return len(self.tool_registry.list_tools())

    @property
    def skills_count(self) -> int:
        return len(self.skill_manager.list_skills())

    def status(self) -> dict:
        """Get kernel status summary."""
        return {
            "tools": self.tools_count,
            "skills": self.skills_count,
            "agents": len(self.registry.list_ids()),
            "policy_pack": self.governor.policy.__class__.__name__,
        }
