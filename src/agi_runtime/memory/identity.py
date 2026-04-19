from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional
from agi_runtime.memory.character_genesis import CharacterSeed, build_initial_character
from pathlib import Path
import json

# MemoryGuard closes the goal-altering drift vector on identity evolution —
# see OWASP Agentic Top 10 2026 ASI06 + ASI10. Imported lazily in
# ``IdentityEngine.evolve`` to avoid a circular import with
# ``agi_runtime.governance``.


@dataclass
class IdentityState:
    name: str = "Lana"
    character: str = "Builder-mentor"
    purpose: str = "Help humans build safe, useful, high-impact agent systems"
    principles: list[str] = None

    def __post_init__(self):
        if self.principles is None:
            self.principles = [
                "Be helpful and truthful",
                "Respect safety boundaries",
                "Prefer measurable outcomes",
            ]


class IdentityEngine:
    def __init__(self, path: str = "memory/identity_state.json", mission: str = "Help humans build safe, useful, high-impact agent systems", style: str = "direct and warm", domain_focus: str = "agent systems", memory_guard: Optional[object] = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.mission = mission
        self.style = style
        self.domain_focus = domain_focus
        # Lazy-import MemoryGuard to avoid a circular dependency.
        if memory_guard is None:
            from agi_runtime.governance.memory_guard import MemoryGuard
            memory_guard = MemoryGuard()
        self._memory_guard = memory_guard
        self.state = self._load()

    def _load(self) -> IdentityState:
        if not self.path.exists():
            return self._build_and_save_default()
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return self._build_and_save_default()
            data = json.loads(raw)
            if not isinstance(data, dict):
                return self._build_and_save_default()
            return IdentityState(**data)
        except Exception:
            return self._build_and_save_default()

    def _build_and_save_default(self) -> IdentityState:
        seed = CharacterSeed(mission=self.mission, style=self.style, domain_focus=self.domain_focus)
        g = build_initial_character(seed)
        s = IdentityState(character=g["archetype"], purpose=g["mission"], principles=g["principles"])
        self._save(s)
        return s

    def _save(self, s: IdentityState):
        self.path.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")

    def evolve(self, observation: str):
        """Evolve identity principles from an observation, under MemoryGuard.

        Principles persist into the agent's system prompt every turn, so a
        malicious principle is a permanent drift vector (OWASP ASI06 +
        ASI10). We route the observation through ``MemoryGuard`` with
        ``kind="principle"`` — the strict mode — and bail out of evolution
        entirely if the observation looks adversarial. We also guard each
        principle string itself before appending, so the stored value is
        a clean, deterministic identifier, not attacker-controlled text.
        """
        if not observation:
            return
        guard_result = self._memory_guard.inspect(observation, kind="principle")
        if guard_result.decision == "deny":
            # Observation is adversarial for a goal-altering write. Skip
            # evolution — the identity state is immutable this turn.
            return
        # For interactions guarded as "sanitize", keep evolving but use the
        # cleaned text for keyword matching. This prevents an attacker
        # from smuggling a keyword *inside* an injection phrase.
        t = (
            guard_result.sanitized_text
            if guard_result.decision == "sanitize" and guard_result.sanitized_text
            else observation
        ).lower()

        if "teach" in t and "learn" in t:
            if "Teach through demos" not in self.state.principles:
                self.state.principles.append("Teach through demos")
        if "speed" in t or "latency" in t:
            if "Minimize end-to-end latency" not in self.state.principles:
                self.state.principles.append("Minimize end-to-end latency")
        self._save(self.state)
