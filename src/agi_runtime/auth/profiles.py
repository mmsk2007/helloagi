from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os
import time
from typing import Any

from agi_runtime.config.env import read_env_file, resolve_env_value


@dataclass
class AuthProfile:
    name: str
    provider: str
    auth_mode: str
    env_key: str
    enabled: bool = True
    priority: int = 100
    description: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuthProfileManager:
    def __init__(self, path: str = "memory/auth_profiles.json", *, env_path: str = ".env"):
        self.path = Path(path)
        self.env_path = env_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"profiles": [], "active_profiles": {}, "updated_at": time.time()}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"profiles": [], "active_profiles": {}, "updated_at": time.time()}
        data.setdefault("profiles", [])
        data.setdefault("active_profiles", {})
        data.setdefault("updated_at", time.time())
        return data

    def save_state(self, state: dict[str, Any]):
        state["updated_at"] = time.time()
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def list_profiles(self, provider: str | None = None) -> list[AuthProfile]:
        state = self.load_state()
        profiles = [AuthProfile(**item) for item in state.get("profiles", [])]
        if provider:
            profiles = [profile for profile in profiles if profile.provider == provider]
        return sorted(profiles, key=lambda profile: (profile.provider, profile.priority, profile.name))

    def get_profile(self, name: str) -> AuthProfile:
        for profile in self.list_profiles():
            if profile.name == name:
                return profile
        raise KeyError(f"Unknown auth profile: {name}")

    def upsert_profile(
        self,
        *,
        name: str,
        provider: str,
        auth_mode: str,
        env_key: str,
        enabled: bool = True,
        priority: int | None = None,
        description: str = "",
        make_active: bool = False,
    ) -> AuthProfile:
        state = self.load_state()
        profiles = state.get("profiles", [])
        now = time.time()
        existing_index = next((index for index, item in enumerate(profiles) if item.get("name") == name), None)
        if priority is None:
            provider_profiles = [item for item in profiles if item.get("provider") == provider]
            priority = max((int(item.get("priority", 100)) for item in provider_profiles), default=99) + 1
        payload = AuthProfile(
            name=name,
            provider=provider,
            auth_mode=auth_mode,
            env_key=env_key,
            enabled=enabled,
            priority=priority,
            description=description,
            created_at=now,
            updated_at=now,
        )
        if existing_index is not None:
            existing = profiles[existing_index]
            payload.created_at = float(existing.get("created_at", now))
            profiles[existing_index] = payload.to_dict()
        else:
            profiles.append(payload.to_dict())
        state["profiles"] = profiles
        if make_active:
            state.setdefault("active_profiles", {})[provider] = name
        self.save_state(state)
        return self.get_profile(name)

    def activate(self, name: str) -> AuthProfile:
        profile = self.get_profile(name)
        state = self.load_state()
        state.setdefault("active_profiles", {})[profile.provider] = profile.name
        for item in state.get("profiles", []):
            if item.get("name") == profile.name:
                item["enabled"] = True
                item["priority"] = 0
                item["updated_at"] = time.time()
            elif item.get("provider") == profile.provider and int(item.get("priority", 100)) == 0:
                item["priority"] = 1
        self.save_state(state)
        return self.get_profile(name)

    def deactivate(self, name: str) -> AuthProfile:
        state = self.load_state()
        profile = self.get_profile(name)
        for item in state.get("profiles", []):
            if item.get("name") == name:
                item["enabled"] = False
                item["updated_at"] = time.time()
        active_profiles = state.setdefault("active_profiles", {})
        if active_profiles.get(profile.provider) == name:
            active_profiles.pop(profile.provider, None)
        self.save_state(state)
        return self.get_profile(name)

    def resolve(self, provider: str) -> dict[str, Any]:
        state = self.load_state()
        active_name = state.get("active_profiles", {}).get(provider)
        candidates = [profile for profile in self.list_profiles(provider) if profile.enabled]
        if active_name:
            candidates.sort(key=lambda profile: (profile.name != active_name, profile.priority, profile.name))
        for profile in candidates:
            secret = resolve_env_value(profile.env_key, self.env_path)
            if secret:
                return {
                    "configured": True,
                    "name": profile.name,
                    "provider": profile.provider,
                    "auth_mode": profile.auth_mode,
                    "env_name": profile.env_key,
                    "secret": secret,
                    "source": "auth_profile",
                }
        return {
            "configured": False,
            "name": active_name,
            "provider": provider,
            "auth_mode": "none",
            "env_name": None,
            "secret": "",
            "source": "auth_profile",
        }

    def doctor(self) -> dict[str, Any]:
        env_file = read_env_file(self.env_path)
        profiles_report: list[dict[str, Any]] = []
        for profile in self.list_profiles():
            source = "process_env" if profile.env_key in os.environ else "local_env" if profile.env_key in env_file else "missing"
            profiles_report.append(
                {
                    **profile.to_dict(),
                    "configured": bool(resolve_env_value(profile.env_key, self.env_path)),
                    "source": source,
                }
            )
        active = self.load_state().get("active_profiles", {})
        return {
            "total": len(profiles_report),
            "active_profiles": active,
            "profiles": profiles_report,
        }

    def ensure_default_profile(self, provider: str, auth_mode: str, env_key: str, description: str = "") -> AuthProfile:
        name = f"{provider}-default"
        return self.upsert_profile(
            name=name,
            provider=provider,
            auth_mode=auth_mode,
            env_key=env_key,
            enabled=True,
            priority=0,
            description=description or f"Default {provider} profile",
            make_active=True,
        )
