"""Policy packs — governance + toolset + identity personas.

Each pack defines not just safety rules, but also which tools are available,
which model tier to use, and what identity traits the agent should exhibit.
This transforms policy packs into full agent personas.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PolicyPack:
    name: str
    deny_keywords: List[str] = field(default_factory=list)
    escalate_keywords: List[str] = field(default_factory=list)
    # Tool restrictions (empty = all tools allowed)
    allowed_tools: List[str] = field(default_factory=list)
    blocked_tools: List[str] = field(default_factory=list)
    # Model preference
    model_tier: str = "balanced"  # speed | balanced | quality
    # Identity traits injected into system prompt
    identity_traits: List[str] = field(default_factory=list)
    # Read-only mode (blocks all write/exec tools)
    read_only: bool = False
    # Max autonomous turns
    max_turns: int = 40
    # Description for display
    description: str = ""


SAFE_DEFAULT = PolicyPack(
    name="safe-default",
    description="Balanced safety with full tool access. Good for general use.",
    deny_keywords=["at whatever cost", "bypass safeguards", "harm", "steal"],
    escalate_keywords=["finance", "medical", "legal", "delete", "production deploy"],
    model_tier="balanced",
    identity_traits=["helpful", "safety-conscious", "practical"],
    max_turns=40,
)

RESEARCH = PolicyPack(
    name="research",
    description="Optimized for web research and analysis. Quality model, web-focused tools.",
    deny_keywords=["harm", "bioweapon", "exploit"],
    escalate_keywords=["clinical", "patient", "financial transfer"],
    allowed_tools=["web_search", "web_fetch", "file_read", "file_write", "file_search",
                    "memory_store", "memory_recall", "session_search", "ask_user",
                    "notify_user", "code_analyze", "python_exec"],
    model_tier="quality",
    identity_traits=["thorough", "evidence-based", "cites-sources", "analytical"],
    max_turns=30,
)

CODER = PolicyPack(
    name="coder",
    description="Full coding capabilities. High-risk tools allowed with governance.",
    deny_keywords=["harm", "steal", "bypass safeguards"],
    escalate_keywords=["delete", "production deploy", "sudo"],
    allowed_tools=["bash_exec", "file_read", "file_write", "file_patch", "file_search",
                    "python_exec", "code_analyze", "web_search", "web_fetch",
                    "memory_store", "memory_recall", "ask_user", "notify_user",
                    "delegate_task", "session_search"],
    model_tier="balanced",
    identity_traits=["precise", "test-driven", "security-aware", "pragmatic"],
    max_turns=40,
)

AGGRESSIVE_BUILDER = PolicyPack(
    name="aggressive-builder",
    description="Maximum autonomy for rapid building. Minimal escalations.",
    deny_keywords=["harm", "steal", "bypass safeguards"],
    escalate_keywords=["delete", "prod database", "payment"],
    model_tier="balanced",
    identity_traits=["fast", "decisive", "ship-it", "iterate-quickly"],
    max_turns=50,
)

REVIEWER = PolicyPack(
    name="reviewer",
    description="Read-only analysis and review. Cannot modify files or execute commands.",
    deny_keywords=["harm", "steal"],
    escalate_keywords=[],
    allowed_tools=["file_read", "file_search", "code_analyze", "memory_recall",
                    "session_search", "web_search", "web_fetch", "ask_user", "notify_user"],
    read_only=True,
    model_tier="quality",
    identity_traits=["critical", "thorough", "constructive", "detail-oriented"],
    max_turns=20,
)

CREATIVE = PolicyPack(
    name="creative",
    description="Creative writing, brainstorming, and ideation. Quality model.",
    deny_keywords=["harm", "steal", "bypass safeguards"],
    escalate_keywords=["finance", "medical", "legal"],
    allowed_tools=["web_search", "web_fetch", "file_read", "file_write",
                    "memory_store", "memory_recall", "ask_user", "notify_user"],
    model_tier="quality",
    identity_traits=["creative", "imaginative", "eloquent", "inspiring"],
    max_turns=25,
)

_PACKS = {
    "safe-default": SAFE_DEFAULT,
    "research": RESEARCH,
    "coder": CODER,
    "aggressive-builder": AGGRESSIVE_BUILDER,
    "reviewer": REVIEWER,
    "creative": CREATIVE,
}


def get_pack(name: str) -> PolicyPack:
    return _PACKS.get(name.lower(), SAFE_DEFAULT)


def list_packs() -> list[PolicyPack]:
    return list(_PACKS.values())
