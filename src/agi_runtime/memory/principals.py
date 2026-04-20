from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional


@dataclass
class PrincipalState:
    principal_id: str
    profile_id: str = ""
    message_count: int = 0
    first_turn_done: bool = False
    bootstrap_completed: bool = False
    preferred_name: str = ""
    response_style: str = ""
    primary_goals: str = ""
    boundaries: str = ""
    timezone: str = ""
    onboarded: bool = False


class PrincipalProfileStore:
    """Per-principal conversational state and bootstrap profile files."""

    def __init__(
        self,
        state_path: str = "memory/principals.json",
        profiles_dir: str = "memory/user_profiles",
    ):
        self.state_path = Path(state_path)
        self.profiles_dir = Path(profiles_dir)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._states: Dict[str, PrincipalState] = {}
        self._load()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        for principal_id, state in raw.items():
            if isinstance(state, dict):
                merged = {"principal_id": principal_id, **state}
                self._states[principal_id] = PrincipalState(**merged)

    def _save(self) -> None:
        payload = {
            pid: {k: v for k, v in asdict(st).items() if k != "principal_id"}
            for pid, st in self._states.items()
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _slug(self, principal_id: str) -> str:
        return hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:12]

    def _normalize_principal_id(self, principal_id: str) -> str:
        principal_id = (principal_id or "local:default").strip() or "local:default"
        return principal_id

    def _get_transport_state(self, principal_id: str) -> PrincipalState:
        principal_id = self._normalize_principal_id(principal_id)
        state = self._states.get(principal_id)
        if state is None:
            state = PrincipalState(principal_id=principal_id)
            self._states[principal_id] = state
            self._save()
        return state

    def resolve_profile_id(self, principal_id: str) -> str:
        current = self._normalize_principal_id(principal_id)
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            state = self._states.get(current)
            if state is None or not state.profile_id:
                return current
            target = self._normalize_principal_id(state.profile_id)
            if target == current:
                return current
            current = target
        return self._normalize_principal_id(principal_id)

    def get(self, principal_id: str) -> PrincipalState:
        resolved = self.resolve_profile_id(principal_id)
        return self._get_transport_state(resolved)

    def update(self, principal_id: str, **fields) -> PrincipalState:
        state = self.get(principal_id)
        for key, value in fields.items():
            if hasattr(state, key) and value is not None:
                setattr(state, key, value)
        self._save()
        return state

    def link_profile(self, principal_id: str, profile_id: str) -> PrincipalState:
        principal_id = self._normalize_principal_id(principal_id)
        profile_id = self.resolve_profile_id(profile_id)
        transport = self._get_transport_state(principal_id)
        if principal_id == profile_id:
            transport.profile_id = ""
        else:
            self._get_transport_state(profile_id)
            transport.profile_id = profile_id
        self._save()
        return self.get(principal_id)

    def record_user_message(self, principal_id: str, text: str) -> PrincipalState:
        state = self.get(principal_id)
        state.message_count += 1
        if state.message_count == 1:
            state.first_turn_done = True
        self._extract_fields(state, text)
        self._ensure_bootstrap_file(state)
        self._maybe_complete_bootstrap(state)
        self._save()
        return state

    def bootstrap_instruction(self, principal_id: str) -> Optional[str]:
        state = self.get(principal_id)
        if state.bootstrap_completed:
            return None
        if state.message_count <= 1:
            return (
                "This is the first interaction with this principal. Keep the intro to 1-2 "
                "sentences, mention /help, and start BOOTSTRAP ritual. Ask exactly one question: "
                "what name they prefer you use."
            )
        if not state.response_style:
            return (
                "Continue BOOTSTRAP ritual. Ask exactly one question about response style "
                "(brief vs detailed, formal vs casual)."
            )
        if not state.primary_goals:
            return (
                "Continue BOOTSTRAP ritual. Ask exactly one question about the user's primary goals."
            )
        if not state.boundaries:
            return (
                "Continue BOOTSTRAP ritual. Ask exactly one question about boundaries and what to avoid."
            )
        return (
            "Finish BOOTSTRAP ritual naturally, summarize preferences in 3-5 bullets, and continue normal assistance."
        )

    def profile_excerpt(self, principal_id: str, max_lines: int = 8) -> Optional[str]:
        state = self.get(principal_id)
        lines = []
        if state.preferred_name:
            lines.append(f"- Preferred name: {state.preferred_name}")
        if state.response_style:
            lines.append(f"- Response style: {state.response_style}")
        if state.primary_goals:
            lines.append(f"- Primary goals: {state.primary_goals}")
        if state.boundaries:
            lines.append(f"- Boundaries: {state.boundaries}")
        if not lines:
            return None
        return "\n".join(lines[:max_lines])

    def _ensure_bootstrap_file(self, state: PrincipalState) -> None:
        slug = self._slug(state.principal_id)
        bootstrap_file = self.profiles_dir / f"{slug}_BOOTSTRAP.md"
        if bootstrap_file.exists() or state.bootstrap_completed:
            return
        bootstrap_file.write_text(
            "# BOOTSTRAP.md\n\n"
            "This principal is in first-run onboarding.\n\n"
            "Collect and persist:\n"
            "1. Preferred name\n"
            "2. Response style\n"
            "3. Primary goals\n"
            "4. Boundaries\n\n"
            "Ask one question at a time and keep tone natural.\n",
            encoding="utf-8",
        )

    def _maybe_complete_bootstrap(self, state: PrincipalState) -> None:
        if state.bootstrap_completed:
            return
        ready = bool(
            state.preferred_name and state.response_style and state.primary_goals and state.boundaries
        )
        if not ready:
            return
        state.bootstrap_completed = True
        slug = self._slug(state.principal_id)

        identity_file = self.profiles_dir / f"{slug}_IDENTITY.md"
        user_file = self.profiles_dir / f"{slug}_USER.md"
        soul_file = self.profiles_dir / f"{slug}_SOUL.md"
        bootstrap_file = self.profiles_dir / f"{slug}_BOOTSTRAP.md"

        identity_file.write_text(
            "# IDENTITY.md\n\n"
            "Agent identity for this principal is guided by SRG-governed autonomy,\n"
            "truthfulness, and practical action-oriented help.\n",
            encoding="utf-8",
        )
        user_file.write_text(
            "# USER.md\n\n"
            f"- Preferred name: {state.preferred_name}\n"
            f"- Response style: {state.response_style}\n"
            f"- Primary goals: {state.primary_goals}\n",
            encoding="utf-8",
        )
        soul_file.write_text(
            "# SOUL.md\n\n"
            "How to behave for this principal:\n"
            f"- Respect boundaries: {state.boundaries}\n"
            "- Keep communication natural and useful.\n"
            "- Use tools when they materially improve outcomes.\n",
            encoding="utf-8",
        )
        if bootstrap_file.exists():
            bootstrap_file.unlink()

    def _extract_fields(self, state: PrincipalState, text: str) -> None:
        t = text.strip()
        low = t.lower()

        if not state.preferred_name:
            m = re.search(r"\b(?:my name is|i am|i'm)\s+([a-zA-Z][a-zA-Z0-9_-]{1,30})", t, re.IGNORECASE)
            if m:
                state.preferred_name = m.group(1)

        if not state.response_style:
            style_tokens = []
            if "brief" in low or "short" in low:
                style_tokens.append("brief")
            if "detailed" in low or "deep" in low:
                style_tokens.append("detailed")
            if "casual" in low or "friendly" in low:
                style_tokens.append("casual")
            if "formal" in low or "professional" in low:
                style_tokens.append("formal")
            if style_tokens:
                state.response_style = ", ".join(dict.fromkeys(style_tokens))

        if not state.primary_goals:
            m = re.search(r"\b(?:i want to|my goal is|help me)\b(.+)", t, re.IGNORECASE)
            if m:
                goal = m.group(1).strip(" .")
                state.primary_goals = goal[:240]

        if not state.boundaries:
            m = re.search(r"\b(?:don't|do not|never|avoid)\b(.+)", t, re.IGNORECASE)
            if m:
                boundaries = m.group(1).strip(" .")
                state.boundaries = boundaries[:240]
