from __future__ import annotations

from dataclasses import dataclass, asdict
from agi_runtime.memory.character_genesis import CharacterSeed, build_initial_character
from pathlib import Path
import json


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
    def __init__(self, path: str = "memory/identity_state.json", mission: str = "Help humans build safe, useful, high-impact agent systems", style: str = "direct and warm", domain_focus: str = "agent systems"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.mission = mission
        self.style = style
        self.domain_focus = domain_focus
        self.state = self._load()

    def _load(self) -> IdentityState:
        if not self.path.exists():
            seed = CharacterSeed(mission=self.mission, style=self.style, domain_focus=self.domain_focus)
            g = build_initial_character(seed)
            s = IdentityState(character=g["archetype"], purpose=g["mission"], principles=g["principles"])
            self._save(s)
            return s
        return IdentityState(**json.loads(self.path.read_text()))

    def _save(self, s: IdentityState):
        self.path.write_text(json.dumps(asdict(s), indent=2))

    def evolve(self, observation: str):
        t = observation.lower()
        if "teach" in t and "learn" in t:
            if "Teach through demos" not in self.state.principles:
                self.state.principles.append("Teach through demos")
        if "speed" in t or "latency" in t:
            if "Minimize end-to-end latency" not in self.state.principles:
                self.state.principles.append("Minimize end-to-end latency")
        self._save(self.state)
