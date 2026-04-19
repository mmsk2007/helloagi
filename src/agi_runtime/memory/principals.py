from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import re
import time

from agi_runtime.governance.memory_guard import MemoryGuard


_NAME_RE = re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z0-9'_-]{0,39})\b", re.IGNORECASE)
_PREFERENCE_RE = re.compile(
    r"\b(?:i prefer|please|prefer)\s+(.{3,160})",
    re.IGNORECASE,
)
_GOAL_RE = re.compile(
    r"\b(?:my goal is|goal:\s*|i want to|help me)\s+(.{3,200})",
    re.IGNORECASE,
)
_BOUNDARY_RE = re.compile(
    r"\b(?:please avoid|don't|do not|never)\s+(.{3,160})",
    re.IGNORECASE,
)


@dataclass
class PrincipalState:
    principal_id: str
    message_count: int = 0
    bootstrap_completed: bool = False
    name: str | None = None
    preferences: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    last_user_message: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class PrincipalProfileStore:
    """Persist lightweight per-principal profile hints for the system prompt.

    This store is intentionally conservative: it keeps only short, sanitized
    summaries extracted from user messages so the agent can maintain first-turn
    onboarding state and basic personalization without persisting raw prompt
    text back into future prompts.
    """

    BOOTSTRAP_MESSAGE_THRESHOLD = 4
    MAX_ITEMS_PER_SECTION = 3

    def __init__(
        self,
        *,
        state_path: str = "memory/principals.json",
        profiles_dir: str = "memory/principal_profiles",
    ):
        self.state_path = Path(state_path)
        self.profiles_dir = Path(profiles_dir)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._guard = MemoryGuard()
        self._states = self._load()

    def _load(self) -> dict[str, PrincipalState]:
        if not self.state_path.exists():
            return {}
        try:
            raw = self.state_path.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            payload = json.loads(raw)
        except Exception:
            return {}

        principals = payload.get("principals", {}) if isinstance(payload, dict) else {}
        if not isinstance(principals, dict):
            return {}

        states: dict[str, PrincipalState] = {}
        for principal_id, item in principals.items():
            if not isinstance(item, dict):
                continue
            try:
                states[str(principal_id)] = PrincipalState(
                    principal_id=str(principal_id),
                    message_count=int(item.get("message_count", 0)),
                    bootstrap_completed=bool(item.get("bootstrap_completed", False)),
                    name=item.get("name"),
                    preferences=list(item.get("preferences", [])),
                    goals=list(item.get("goals", [])),
                    boundaries=list(item.get("boundaries", [])),
                    last_user_message=str(item.get("last_user_message", "")),
                    created_at=float(item.get("created_at", time.time())),
                    updated_at=float(item.get("updated_at", time.time())),
                )
            except Exception:
                continue
        return states

    def _save(self) -> None:
        payload = {
            "principals": {
                principal_id: asdict(state)
                for principal_id, state in sorted(self._states.items())
            }
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _profile_path(self, principal_id: str) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", principal_id).strip("._")
        if not safe_name:
            safe_name = "unknown"
        return self.profiles_dir / f"{safe_name}.json"

    def _save_profile_doc(self, state: PrincipalState) -> None:
        self._profile_path(state.principal_id).write_text(
            json.dumps(asdict(state), indent=2),
            encoding="utf-8",
        )

    def _state_for(self, principal_id: str) -> PrincipalState:
        pid = (principal_id or "local:default").strip() or "local:default"
        return self._states.setdefault(pid, PrincipalState(principal_id=pid))

    def get(self, principal_id: str) -> PrincipalState:
        return self._state_for(principal_id)

    def _sanitize_summary(self, text: str) -> str | None:
        if not text:
            return None
        cleaned = self._guard.safe_text(text.strip(), kind="summary")
        if not cleaned:
            return None
        cleaned = " ".join(cleaned.split())
        return cleaned[:200] if cleaned else None

    @staticmethod
    def _append_unique(items: list[str], value: str | None, *, limit: int) -> None:
        if not value:
            return
        if value in items:
            return
        items.append(value)
        if len(items) > limit:
            del items[:-limit]

    def _extract_name(self, text: str) -> str | None:
        match = _NAME_RE.search(text)
        if not match:
            return None
        return self._sanitize_summary(match.group(1))

    def _extract_preference(self, text: str) -> str | None:
        match = _PREFERENCE_RE.search(text)
        if not match:
            return None
        return self._sanitize_summary(match.group(1))

    def _extract_goal(self, text: str) -> str | None:
        match = _GOAL_RE.search(text)
        if not match:
            return None
        return self._sanitize_summary(match.group(1))

    def _extract_boundary(self, text: str) -> str | None:
        match = _BOUNDARY_RE.search(text)
        if not match:
            return None
        return self._sanitize_summary(match.group(1))

    def record_user_message(self, principal_id: str, text: str) -> None:
        state = self._state_for(principal_id)
        safe_last_message = self._sanitize_summary(text or "")

        state.message_count += 1
        state.updated_at = time.time()
        if safe_last_message:
            state.last_user_message = safe_last_message

        extracted_name = self._extract_name(text or "")
        if extracted_name:
            state.name = extracted_name

        self._append_unique(
            state.preferences,
            self._extract_preference(text or ""),
            limit=self.MAX_ITEMS_PER_SECTION,
        )
        self._append_unique(
            state.goals,
            self._extract_goal(text or ""),
            limit=self.MAX_ITEMS_PER_SECTION,
        )
        self._append_unique(
            state.boundaries,
            self._extract_boundary(text or ""),
            limit=self.MAX_ITEMS_PER_SECTION,
        )

        if state.message_count >= self.BOOTSTRAP_MESSAGE_THRESHOLD:
            state.bootstrap_completed = True

        self._save()
        self._save_profile_doc(state)

    def bootstrap_instruction(self, principal_id: str) -> str | None:
        state = self._state_for(principal_id)
        if state.bootstrap_completed:
            return None
        return (
            "This looks like an early interaction with this principal. "
            "Be briefly welcoming, learn their goal and preferred style through normal conversation, "
            "and mention that /help is available if they want command guidance."
        )

    def profile_excerpt(self, principal_id: str) -> str | None:
        state = self._state_for(principal_id)
        parts: list[str] = []

        if state.name:
            parts.append(f"Known name: {state.name}")
        if state.preferences:
            parts.append("Preferences: " + "; ".join(state.preferences[-self.MAX_ITEMS_PER_SECTION:]))
        if state.goals:
            parts.append("Goals: " + "; ".join(state.goals[-self.MAX_ITEMS_PER_SECTION:]))
        if state.boundaries:
            parts.append("Boundaries: " + "; ".join(state.boundaries[-self.MAX_ITEMS_PER_SECTION:]))

        if not parts:
            return None
        return "\n".join(parts)


__all__ = ["PrincipalProfileStore", "PrincipalState"]
