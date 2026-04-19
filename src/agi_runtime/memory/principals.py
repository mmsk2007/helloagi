from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class PrincipalProfile:
    """Persisted per-principal bootstrap/profile state."""

    principal_id: str
    bootstrap_completed: bool = False
    message_count: int = 0
    user_name: Optional[str] = None
    communication_style: Optional[str] = None
    goal: Optional[str] = None
    safety_preferences: Optional[str] = None
    recent_messages: list[str] = field(default_factory=list)


class PrincipalProfileStore:
    """Track lightweight per-principal profile/bootstrap state.

    The agent uses this store to keep first-turn onboarding guidance scoped
    to the active principal and to surface a compact profile excerpt into the
    system prompt once the user has shared stable preferences.
    """

    def __init__(
        self,
        state_path: str = "memory/principals.json",
        profiles_dir: str = "memory/profiles",
    ) -> None:
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._profiles: Dict[str, PrincipalProfile] = self._load()

    def get(self, principal_id: str) -> PrincipalProfile:
        pid = self._normalize_principal_id(principal_id)
        profile = self._profiles.get(pid)
        if profile is None:
            profile = PrincipalProfile(principal_id=pid)
            self._profiles[pid] = profile
            self._save()
        return profile

    def record_user_message(self, principal_id: str, text: str) -> None:
        profile = self.get(principal_id)
        message = (text or "").strip()
        if not message:
            return

        profile.message_count += 1
        profile.recent_messages.append(message[:300])
        profile.recent_messages = profile.recent_messages[-10:]

        extracted_name = self._extract_name(message)
        if extracted_name:
            profile.user_name = extracted_name

        extracted_style = self._extract_style(message)
        if extracted_style:
            profile.communication_style = extracted_style

        extracted_goal = self._extract_goal(message)
        if extracted_goal:
            profile.goal = extracted_goal

        extracted_safety = self._extract_safety_preference(message)
        if extracted_safety:
            profile.safety_preferences = extracted_safety

        profile.bootstrap_completed = all(
            (
                profile.user_name,
                profile.communication_style,
                profile.goal,
                profile.safety_preferences,
            )
        )
        self._save()

    def bootstrap_instruction(self, principal_id: str) -> Optional[str]:
        profile = self.get(principal_id)
        if profile.bootstrap_completed:
            return None

        missing = []
        if not profile.user_name:
            missing.append("what to call you")
        if not profile.communication_style:
            missing.append("your preferred response style")
        if not profile.goal:
            missing.append("your current goal")
        if not profile.safety_preferences:
            missing.append("any constraints or risky actions to avoid")

        missing_text = ", ".join(missing)
        return (
            "This looks like an early conversation with this principal. Keep the"
            " reply helpful and lightweight, and gather missing context naturally"
            f" when useful: {missing_text}. Mention /help only if the user seems"
            " unsure how to proceed."
        )

    def profile_excerpt(self, principal_id: str) -> Optional[str]:
        profile = self.get(principal_id)
        lines = []
        if profile.user_name:
            lines.append(f"Name: {profile.user_name}")
        if profile.communication_style:
            lines.append(f"Preferred style: {profile.communication_style}")
        if profile.goal:
            lines.append(f"Current goal: {profile.goal}")
        if profile.safety_preferences:
            lines.append(f"Constraints: {profile.safety_preferences}")
        if not lines:
            return None
        return "\n".join(lines)

    def _load(self) -> Dict[str, PrincipalProfile]:
        if not self.state_path.exists():
            return {}
        try:
            raw = self.state_path.read_text(encoding="utf-8").strip()
            if not raw:
                return {}
            data = json.loads(raw)
        except Exception:
            return {}

        if not isinstance(data, dict):
            return {}

        profiles: Dict[str, PrincipalProfile] = {}
        for pid, payload in data.items():
            if not isinstance(payload, dict):
                continue
            payload = dict(payload)
            payload["principal_id"] = self._normalize_principal_id(
                payload.get("principal_id") or pid
            )
            try:
                profile = PrincipalProfile(**payload)
            except TypeError:
                continue
            profiles[profile.principal_id] = profile
        return profiles

    def _save(self) -> None:
        serialized = {
            pid: asdict(profile)
            for pid, profile in sorted(self._profiles.items())
        }
        self.state_path.write_text(
            json.dumps(serialized, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        for profile in self._profiles.values():
            self._profile_path(profile.principal_id).write_text(
                json.dumps(asdict(profile), indent=2, sort_keys=True),
                encoding="utf-8",
            )

    @staticmethod
    def _normalize_principal_id(principal_id: str) -> str:
        pid = str(principal_id or "local:default").strip()
        return pid or "local:default"

    def _profile_path(self, principal_id: str) -> Path:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", principal_id).strip("_")
        if not safe_name:
            safe_name = "local_default"
        return self.profiles_dir / f"{safe_name}.json"

    @staticmethod
    def _extract_name(text: str) -> Optional[str]:
        patterns = (
            r"\bmy name is\s+([A-Za-z][A-Za-z0-9_-]{1,31})\b",
            r"\bi am\s+([A-Za-z][A-Za-z0-9_-]{1,31})\b",
            r"\bi'm\s+([A-Za-z][A-Za-z0-9_-]{1,31})\b",
        )
        lowered = text.strip()
        for pattern in patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value[:1].upper() + value[1:]
        return None

    @staticmethod
    def _extract_style(text: str) -> Optional[str]:
        patterns = (
            r"\bi prefer\s+(.+?)\s+responses?\b",
            r"\bprefer\s+(.+?)\s+responses?\b",
            r"\brespond\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .")
                if value:
                    return f"{value} responses"
        return None

    @staticmethod
    def _extract_goal(text: str) -> Optional[str]:
        patterns = (
            r"\bmy goal is\s+(.+)$",
            r"\bgoal:\s+(.+)$",
            r"\bi want to\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .")
                if value:
                    return value
        return None

    @staticmethod
    def _extract_safety_preference(text: str) -> Optional[str]:
        patterns = (
            r"\bplease avoid\s+(.+)$",
            r"\bavoid\s+(.+)$",
            r"\bdon't\s+(.+)$",
            r"\bdo not\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .")
                if value:
                    return value
        return None


__all__ = ["PrincipalProfile", "PrincipalProfileStore"]
