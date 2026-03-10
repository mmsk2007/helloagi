from dataclasses import dataclass, field


@dataclass
class PolicyPack:
    name: str
    deny_keywords: list[str] = field(default_factory=list)
    escalate_keywords: list[str] = field(default_factory=list)


SAFE_DEFAULT = PolicyPack(
    name="safe-default",
    deny_keywords=["at whatever cost", "bypass safeguards", "harm", "steal"],
    escalate_keywords=["finance", "medical", "legal", "delete", "production deploy"],
)

RESEARCH = PolicyPack(
    name="research",
    deny_keywords=["harm", "bioweapon", "exploit"],
    escalate_keywords=["clinical", "patient", "financial transfer"],
)

AGGRESSIVE_BUILDER = PolicyPack(
    name="aggressive-builder",
    deny_keywords=["harm", "steal", "bypass safeguards"],
    escalate_keywords=["delete", "prod database", "payment"],
)


def get_pack(name: str) -> PolicyPack:
    n = name.lower()
    if n == "research":
        return RESEARCH
    if n == "aggressive-builder":
        return AGGRESSIVE_BUILDER
    return SAFE_DEFAULT
