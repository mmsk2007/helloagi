from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import json
import re
import time


_MAX_RECENT_MESSAGES = 8


@dataclass
class PrincipalState:
    preferred_name: str = ""
    timezone: str = ""
    onboarded: bool = False
    bootstrap_completed: bool = False
    message_count: int = 0
    communication_style: str = ""
    goal: str = ""
    safety_preferences: str = ""
    recent_messages: List[str] = field(default_factory=list)
    updated_at: float = 0.0


class PrincipalProfileStore:
    """Persistent per-principal profile and first-turn bootstrap state."""

    def __init__(
        self,
        state_path: str = "memory/principals.json",
        profiles_dir: str = "memory/principal_profiles",
    ):
        self.state_path = Path(state_path)
        self.profiles_dir = Path(profiles_dir)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._states: Dict[str, PrincipalState] = self._load()

    def get(self, principal_id: str) -> PrincipalState:
        pid = self._normalize_principal_id(principal_id)
        if pid not in self._states:
            self._states[pid] = PrincipalState()
        return self._states[pid]

    def update(self, principal_id: str, **changes) -> PrincipalState:
        state = self.get(principal_id)
        allowed = {field_name for field_name in PrincipalState.__dataclass_fields__}
        for key, value in changes.items():
            if key in allowed:
                setattr(state, key, value)
        self._refresh_bootstrap(state)
        self._touch(state)
        self._save()
        self._write_profile_snapshot(self._normalize_principal_id(principal_id), state)
        return state

    def record_user_message(self, principal_id: str, message: str) -> PrincipalState:
        state = self.get(principal_id)
        text = self._clean_text(message)
        if not text:
            return state

        state.message_count += 1
        state.recent_messages.append(text)
        if len(state.recent_messages) > _MAX_RECENT_MESSAGES:
            state.recent_messages = state.recent_messages[-_MAX_RECENT_MESSAGES:]

        self._extract_profile_hints(state, text)
        self._refresh_bootstrap(state)
        self._touch(state)
        pid = self._normalize_principal_id(principal_id)
        self._save()
        self._write_profile_snapshot(pid, state)
        return state

    def bootstrap_instruction(self, principal_id: str) -> Optional[str]:
        state = self.get(principal_id)
        if state.bootstrap_completed:
            return None

        missing: List[str] = []
        if not state.preferred_name:
            missing.append("their preferred name")
        if not state.communication_style:
            missing.append("how they like responses to sound")
        if not state.goal:
            missing.append("their current goal")
        if not state.safety_preferences:
            missing.append("any constraints or actions to avoid")

        focus = ", ".join(missing[:3]) if missing else "their working preferences"
        return (
            "You are still learning this principal. "
            f"When it fits naturally, ask a brief follow-up to learn {focus}. "
            "Keep it conversational, avoid interrogating them, and remind them that /help is available."
        )

    def profile_excerpt(self, principal_id: str) -> Optional[str]:
        state = self.get(principal_id)
        lines: List[str] = []
        if state.preferred_name:
            lines.append(f"Preferred name: {state.preferred_name}")
        if state.timezone:
            lines.append(f"Timezone: {state.timezone}")
        if state.communication_style:
            lines.append(f"Response style: {state.communication_style}")
        if state.goal:
            lines.append(f"Current goal: {state.goal}")
        if state.safety_preferences:
            lines.append(f"Safety preferences: {state.safety_preferences}")
        if not lines:
            return None
        return "\n".join(lines)

    def _load(self) -> Dict[str, PrincipalState]:
        if not self.state_path.exists():
            return {}
        try:
            raw = self.state_path.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            payload = json.loads(raw)
            if isinstance(payload, dict) and "principals" in payload:
                payload = payload.get("principals", {})
            if not isinstance(payload, dict):
                return {}
            states: Dict[str, PrincipalState] = {}
            allowed = {field_name for field_name in PrincipalState.__dataclass_fields__}
            for principal_id, data in payload.items():
                if not isinstance(data, dict):
                    continue
                filtered = {k: v for k, v in data.items() if k in allowed}
                states[str(principal_id)] = PrincipalState(**filtered)
            return states
        except Exception:
            return {}

    def _save(self) -> None:
        payload = {
            "version": 1,
            "principals": {principal_id: asdict(state) for principal_id, state in self._states.items()},
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_profile_snapshot(self, principal_id: str, state: PrincipalState) -> None:
        snapshot_path = self.profiles_dir / f"{self._slugify(principal_id)}.json"
        snapshot_path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")

    def _extract_profile_hints(self, state: PrincipalState, text: str) -> None:
        lowered = text.lower()

        if not state.preferred_name:
            for pattern in (
                r"\bmy name is ([a-z][a-z0-9 '\-]{0,40})",
                r"\bcall me ([a-z][a-z0-9 '\-]{0,40})",
                r"\bi am ([a-z][a-z0-9 '\-]{0,40})\b",
                r"\bi'm ([a-z][a-z0-9 '\-]{0,40})\b",
            ):
                match = re.search(pattern, lowered, flags=re.IGNORECASE)
                if match:
                    state.preferred_name = self._title_case_name(match.group(1))
                    break

        if not state.communication_style:
            style = self._extract_with_prefix(
                lowered,
                ("i prefer ", "please respond ", "respond in a ", "be "),
            )
            if style and any(token in style for token in ("brief", "casual", "formal", "concise", "detailed", "direct")):
                state.communication_style = style

        if not state.goal:
            goal = self._extract_with_prefix(
                lowered,
                ("my goal is ", "i want to ", "i need to ", "help me "),
            )
            if goal:
                state.goal = goal

        if not state.safety_preferences:
            safety = self._extract_with_prefix(
                lowered,
                ("please avoid ", "avoid ", "do not ", "don't "),
            )
            if safety:
                prefix = "avoid " if not safety.startswith(("avoid ", "do not ", "don't ")) else ""
                state.safety_preferences = f"{prefix}{safety}".strip()

    def _refresh_bootstrap(self, state: PrincipalState) -> None:
        known_fields = sum(
            1
            for value in (
                state.preferred_name,
                state.communication_style,
                state.goal,
                state.safety_preferences,
            )
            if bool(str(value).strip())
        )
        state.bootstrap_completed = known_fields >= 3 or state.message_count >= 5

    @staticmethod
    def _normalize_principal_id(principal_id: str) -> str:
        pid = (principal_id or "").strip()
        return pid or "local:default"

    @staticmethod
    def _clean_text(text: str) -> str:
        return " ".join((text or "").strip().split())

    @staticmethod
    def _extract_with_prefix(text: str, prefixes: tuple[str, ...]) -> str:
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix):].strip(" .,!?:;")
            idx = text.find(prefix)
            if idx != -1:
                return text[idx + len(prefix):].strip(" .,!?:;")
        return ""

    @staticmethod
    def _title_case_name(name: str) -> str:
        cleaned = " ".join(name.strip(" .,!?:;").split())
        parts = [part.capitalize() for part in cleaned.split()[:4]]
        return " ".join(parts)

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._")
        return slug or "principal"

    @staticmethod
    def _touch(state: PrincipalState) -> None:
        state.updated_at = time.time()
