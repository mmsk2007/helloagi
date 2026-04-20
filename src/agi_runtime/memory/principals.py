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
    preferred_name: str = ""
    timezone: str = ""
    onboarded: bool = False
    preferences: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    last_user_message: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class PrincipalProfileStore:
    """Persist lightweight per-principal profile hints for the system prompt."""

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

    @staticmethod
    def resolve_profile_id(principal_id: str) -> str:
        """Normalize chat-scoped principals to a stable per-user profile id."""
        pid = (principal_id or "local:default").strip() or "local:default"
        parts = pid.split(":")

        if len(parts) >= 5 and parts[0] == "telegram" and parts[1] == "group" and parts[3] == "user":
            return f"telegram:user:{parts[4]}"
        if len(parts) >= 3 and parts[0] == "telegram" and parts[1] == "dm":
            return f"telegram:user:{parts[2]}"
        if len(parts) >= 5 and parts[0] == "discord" and parts[1] == "channel" and parts[3] == "user":
            return f"discord:user:{parts[4]}"
        if len(parts) >= 3 and parts[0] == "discord" and parts[1] == "dm":
            return f"discord:user:{parts[2]}"
        return pid

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
                source_id = str(principal_id)
                pid = self.resolve_profile_id(source_id)
                preferred_name = str(item.get("preferred_name", "") or "")
                legacy_name = item.get("name")
                loaded = PrincipalState(
                    principal_id=pid,
                    message_count=int(item.get("message_count", 0)),
                    bootstrap_completed=bool(item.get("bootstrap_completed", False)),
                    name=str(legacy_name) if legacy_name is not None else None,
                    preferred_name=preferred_name,
                    timezone=str(item.get("timezone", "") or ""),
                    onboarded=bool(item.get("onboarded", False)),
                    preferences=list(item.get("preferences", [])),
                    goals=list(item.get("goals", [])),
                    boundaries=list(item.get("boundaries", [])),
                    last_user_message=str(item.get("last_user_message", "")),
                    created_at=float(item.get("created_at", time.time())),
                    updated_at=float(item.get("updated_at", time.time())),
                )
                if not loaded.preferred_name and loaded.name:
                    loaded.preferred_name = loaded.name
                existing = states.get(pid)
                states[pid] = loaded if existing is None else self._merge_states(existing, loaded)
            except Exception:
                continue
        return states

    def _merge_states(self, left: PrincipalState, right: PrincipalState) -> PrincipalState:
        newer = right if right.updated_at >= left.updated_at else left
        older = left if newer is right else right
        return PrincipalState(
            principal_id=newer.principal_id,
            message_count=left.message_count + right.message_count,
            bootstrap_completed=left.bootstrap_completed or right.bootstrap_completed,
            name=newer.name or older.name,
            preferred_name=newer.preferred_name or older.preferred_name,
            timezone=newer.timezone or older.timezone,
            onboarded=left.onboarded or right.onboarded,
            preferences=self._merge_unique_items(left.preferences, right.preferences),
            goals=self._merge_unique_items(left.goals, right.goals),
            boundaries=self._merge_unique_items(left.boundaries, right.boundaries),
            last_user_message=newer.last_user_message or older.last_user_message,
            created_at=min(left.created_at, right.created_at),
            updated_at=max(left.updated_at, right.updated_at),
        )

    def _merge_unique_items(self, left: list[str], right: list[str]) -> list[str]:
        merged: list[str] = []
        for value in [*left, *right]:
            clean = str(value or "").strip()
            if not clean or clean in merged:
                continue
            merged.append(clean)
        return merged[-self.MAX_ITEMS_PER_SECTION :]

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
        pid = self.resolve_profile_id(principal_id)
        return self._states.setdefault(pid, PrincipalState(principal_id=pid))

    def get(self, principal_id: str) -> PrincipalState:
        return self._state_for(principal_id)

    def update(
        self,
        principal_id: str,
        *,
        preferred_name: str | None = None,
        timezone: str | None = None,
        onboarded: bool | None = None,
    ) -> PrincipalState:
        state = self._state_for(principal_id)
        state.updated_at = time.time()
        if preferred_name is not None:
            clean_name = self._sanitize_summary(preferred_name) or ""
            state.preferred_name = clean_name
            state.name = clean_name or state.name
        if timezone is not None:
            state.timezone = str(timezone or "").strip()
        if onboarded is not None:
            state.onboarded = bool(onboarded)
        self._save()
        self._save_profile_doc(state)
        return state

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
        if not value or value in items:
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
            if not state.preferred_name:
                state.preferred_name = extracted_name

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

        if state.preferred_name:
            parts.append(f"Preferred name: {state.preferred_name}")
        elif state.name:
            parts.append(f"Known name: {state.name}")
        if state.timezone:
            parts.append(f"Timezone: {state.timezone}")
        if state.preferences:
            parts.append("Preferences: " + "; ".join(state.preferences[-self.MAX_ITEMS_PER_SECTION :]))
        if state.goals:
            parts.append("Goals: " + "; ".join(state.goals[-self.MAX_ITEMS_PER_SECTION :]))
        if state.boundaries:
            parts.append("Boundaries: " + "; ".join(state.boundaries[-self.MAX_ITEMS_PER_SECTION :]))

        if not parts:
            return None
        return "\n".join(parts)


__all__ = ["PrincipalProfileStore", "PrincipalState"]
