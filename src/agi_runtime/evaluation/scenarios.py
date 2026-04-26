"""Named evaluation scenarios (stubs for future benchmark runner)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Scenario:
    id: str
    title: str
    prompt: str
    expect: List[str]


LONG_HORIZON = Scenario(
    id="long_horizon",
    title="Research and compare frameworks",
    prompt="Research three AI agent frameworks, compare architecture, recommend one.",
    expect=["plan", "tools", "structured"],
)

SKILL_REUSE = Scenario(
    id="skill_reuse",
    title="Repeatable report",
    prompt="Create a repository analysis report; then repeat for another repo.",
    expect=["skill", "reuse"],
)


def all_scenarios() -> List[Scenario]:
    return [LONG_HORIZON, SKILL_REUSE]
