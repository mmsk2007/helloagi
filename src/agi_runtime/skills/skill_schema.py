"""Skill Contract schema — the formal specification of a learned skill.

Inspired by COS-PLAY's skill contracts: preconditions, execution steps,
success criteria, failure modes, and confidence scoring.  Every skill is
a first-class, versionable, governable object.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SkillContract:
    """A reusable, governed skill with full lifecycle metadata."""

    # Identity
    skill_id: str = ""
    name: str = ""
    description: str = ""
    task_type: str = ""  # "file_ops", "coding", "web_research", "system", "general"

    # Specification (COSPLAY-inspired)
    preconditions: List[str] = field(default_factory=list)
    execution_steps: List[str] = field(default_factory=list)
    tools_required: List[str] = field(default_factory=list)
    expected_observations: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    failure_modes: List[str] = field(default_factory=list)
    recovery_strategy: str = ""

    # Triggers (backward-compat with old SkillManager)
    triggers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # Scoring
    confidence_score: float = 0.5  # 0.0-1.0
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    # Governance
    srg_risk_level: str = "low"  # "low", "medium", "high"
    status: str = "candidate"   # "candidate", "active", "retired", "archived"

    # Provenance
    created_from_task_id: str = ""
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    last_used_at: float = 0.0

    def __post_init__(self):
        if not self.skill_id:
            self.skill_id = str(uuid.uuid4())[:12]
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    # ── Scoring ──────────────────────────────────────────────────

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    def record_success(self) -> None:
        self.usage_count += 1
        self.success_count += 1
        self.last_used_at = time.time()
        self.updated_at = time.time()
        self._recompute_confidence()

    def record_failure(self, failure_mode: str = "") -> None:
        self.usage_count += 1
        self.failure_count += 1
        self.last_used_at = time.time()
        self.updated_at = time.time()
        if failure_mode and failure_mode not in self.failure_modes:
            self.failure_modes.append(failure_mode)
        self._recompute_confidence()

    def _recompute_confidence(self) -> None:
        """Confidence = weighted success rate with recency bias."""
        total = self.success_count + self.failure_count
        if total == 0:
            self.confidence_score = 0.5
            return
        base = self.success_count / total
        # Recency: if used recently, slight boost; if stale, slight penalty
        age_days = (time.time() - self.last_used_at) / 86400 if self.last_used_at else 30
        recency = max(0.0, 1.0 - (age_days / 60))  # decays to 0 over 60 days
        self.confidence_score = round(0.7 * base + 0.3 * recency, 3)

    # ── Risk Computation ─────────────────────────────────────────

    HIGH_RISK_TOOLS = {"bash_exec", "python_exec", "browser_exec_js", "delegate_task"}
    MEDIUM_RISK_TOOLS = {
        "file_write", "file_patch", "web_fetch", "browser_navigate",
        "browser_click", "browser_type", "send_file_tool",
    }

    def compute_risk_level(self) -> str:
        """Derive SRG risk level from the tools this skill requires."""
        tools = set(self.tools_required)
        if tools & self.HIGH_RISK_TOOLS:
            self.srg_risk_level = "high"
        elif tools & self.MEDIUM_RISK_TOOLS:
            self.srg_risk_level = "medium"
        else:
            self.srg_risk_level = "low"
        return self.srg_risk_level

    # ── Serialization ────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> SkillContract:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, text: str) -> SkillContract:
        return cls.from_dict(json.loads(text))

    def to_markdown(self) -> str:
        """Serialize as markdown with YAML frontmatter (backward-compat)."""
        triggers_str = "[" + ", ".join(self.triggers) + "]"
        tools_str = "[" + ", ".join(self.tools_required) + "]"
        tags_str = "[" + ", ".join(self.tags) + "]"
        front = (
            f"---\n"
            f"skill_id: {self.skill_id}\n"
            f"name: {self.name}\n"
            f"description: {self.description}\n"
            f"task_type: {self.task_type}\n"
            f"triggers: {triggers_str}\n"
            f"tools: {tools_str}\n"
            f"tags: {tags_str}\n"
            f"confidence: {self.confidence_score}\n"
            f"usage_count: {self.usage_count}\n"
            f"success_count: {self.success_count}\n"
            f"failure_count: {self.failure_count}\n"
            f"srg_risk_level: {self.srg_risk_level}\n"
            f"status: {self.status}\n"
            f"version: {self.version}\n"
            f"created_at: {self.created_at}\n"
            f"---\n\n"
        )
        body_parts = []
        if self.preconditions:
            body_parts.append("## Preconditions\n" + "\n".join(f"- {p}" for p in self.preconditions))
        if self.execution_steps:
            body_parts.append("## Steps\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(self.execution_steps)))
        if self.success_criteria:
            body_parts.append("## Success Criteria\n" + "\n".join(f"- {c}" for c in self.success_criteria))
        if self.failure_modes:
            body_parts.append("## Failure Modes\n" + "\n".join(f"- {f}" for f in self.failure_modes))
        if self.recovery_strategy:
            body_parts.append(f"## Recovery\n{self.recovery_strategy}")
        return front + "\n\n".join(body_parts) + "\n"

    # ── Display ──────────────────────────────────────────────────

    def short_summary(self) -> str:
        return (
            f"[{self.status}] {self.name} (conf={self.confidence_score:.2f}, "
            f"used={self.usage_count}, risk={self.srg_risk_level})"
        )

    def to_prompt_injection(self) -> str:
        """Format for injection into agent system prompt."""
        lines = [f"Skill: {self.name} — {self.description}"]
        if self.preconditions:
            lines.append(f"  Use when: {'; '.join(self.preconditions[:3])}")
        if self.execution_steps:
            lines.append(f"  Steps: {'; '.join(self.execution_steps[:5])}")
        if self.tools_required:
            lines.append(f"  Tools: {', '.join(self.tools_required)}")
        return "\n".join(lines)


__all__ = ["SkillContract"]
