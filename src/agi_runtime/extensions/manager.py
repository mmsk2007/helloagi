from __future__ import annotations

from dataclasses import asdict, dataclass, field
from importlib import import_module
from pathlib import Path
import json
import os
from typing import Any

from agi_runtime.config.env import load_local_env
from agi_runtime.utils.imports import module_available


@dataclass(frozen=True)
class ExtensionManifest:
    name: str
    title: str
    category: str
    description: str
    required_env: list[str] = field(default_factory=list)
    python_modules: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)
    factory_path: str | None = None
    default_enabled: bool = False


@dataclass
class ExtensionStatus:
    name: str
    title: str
    category: str
    description: str
    enabled: bool
    available: bool
    missing_env: list[str] = field(default_factory=list)
    missing_modules: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _build_telegram_channel(agent):
    from agi_runtime.channels.telegram import TelegramChannel

    return TelegramChannel(agent)


def _build_discord_channel(agent):
    from agi_runtime.channels.discord import DiscordChannel

    return DiscordChannel(agent)


class ExtensionManager:
    def __init__(self, state_path: str = "memory/extensions_state.json"):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._manifests = {
            manifest.name: manifest
            for manifest in [
                ExtensionManifest(
                    name="telegram",
                    title="Telegram Bot",
                    category="channel",
                    description="Deliver HelloAGI through a Telegram bot with reminders and approvals.",
                    required_env=["TELEGRAM_BOT_TOKEN"],
                    python_modules=["telegram"],
                    extras=["helloagi[telegram]"],
                    factory_path="agi_runtime.extensions.manager:_build_telegram_channel",
                ),
                ExtensionManifest(
                    name="discord",
                    title="Discord Bot",
                    category="channel",
                    description="Deliver HelloAGI through Discord slash commands, DMs, and mentions.",
                    required_env=["DISCORD_BOT_TOKEN"],
                    python_modules=["discord"],
                    extras=["helloagi[discord]"],
                    factory_path="agi_runtime.extensions.manager:_build_discord_channel",
                ),
                ExtensionManifest(
                    name="embeddings",
                    title="Semantic Memory",
                    category="capability",
                    description="Enable semantic memory and embeddings-backed recall for long-term agent context.",
                    required_env=["GOOGLE_API_KEY"],
                    python_modules=["google.genai"],
                    extras=["helloagi[embeddings]"],
                ),
            ]
        }

    def manifests(self) -> list[ExtensionManifest]:
        return list(self._manifests.values())

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"enabled": []}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"enabled": []}
        enabled = data.get("enabled", [])
        if not isinstance(enabled, list):
            enabled = []
        return {"enabled": [str(name) for name in enabled if str(name) in self._manifests]}

    def save_state(self, state: dict[str, Any]):
        enabled = [name for name in state.get("enabled", []) if name in self._manifests]
        self.state_path.write_text(json.dumps({"enabled": enabled}, indent=2), encoding="utf-8")

    def enabled_names(self, *, category: str | None = None) -> list[str]:
        enabled = self.load_state().get("enabled", [])
        if category is None:
            return list(enabled)
        return [name for name in enabled if self._manifests[name].category == category]

    def enable(self, name: str) -> ExtensionStatus:
        manifest = self.require(name)
        state = self.load_state()
        enabled = set(state.get("enabled", []))
        enabled.add(manifest.name)
        self.save_state({"enabled": sorted(enabled)})
        return self.status(manifest.name)

    def disable(self, name: str) -> ExtensionStatus:
        manifest = self.require(name)
        state = self.load_state()
        enabled = [item for item in state.get("enabled", []) if item != manifest.name]
        self.save_state({"enabled": enabled})
        return self.status(manifest.name)

    def require(self, name: str) -> ExtensionManifest:
        if name not in self._manifests:
            raise KeyError(f"Unknown extension: {name}")
        return self._manifests[name]

    def status(self, name: str) -> ExtensionStatus:
        load_local_env()
        manifest = self.require(name)
        enabled = manifest.name in self.enabled_names()
        missing_env = [env_name for env_name in manifest.required_env if not os.environ.get(env_name)]
        missing_modules = [
            module_name for module_name in manifest.python_modules
            if not module_available(module_name)
        ]
        available = not missing_env and not missing_modules
        notes: list[str] = []
        if missing_env:
            notes.append(f"Set: {', '.join(missing_env)}")
        if missing_modules:
            notes.append("Install extra: " + ", ".join(manifest.extras or manifest.python_modules))
        return ExtensionStatus(
            name=manifest.name,
            title=manifest.title,
            category=manifest.category,
            description=manifest.description,
            enabled=enabled,
            available=available,
            missing_env=missing_env,
            missing_modules=missing_modules,
            extras=manifest.extras,
            notes=notes,
        )

    def list_extensions(self, *, enabled_only: bool = False, category: str | None = None) -> list[ExtensionStatus]:
        statuses: list[ExtensionStatus] = []
        for manifest in self.manifests():
            if category is not None and manifest.category != category:
                continue
            status = self.status(manifest.name)
            if enabled_only and not status.enabled:
                continue
            statuses.append(status)
        return statuses

    def doctor(self, *, enabled_only: bool = False) -> dict[str, Any]:
        statuses = self.list_extensions(enabled_only=enabled_only)
        available = sum(1 for item in statuses if item.available)
        enabled = sum(1 for item in statuses if item.enabled)
        return {
            "total": len(statuses),
            "enabled": enabled,
            "healthy": available,
            "extensions": [asdict(item) for item in statuses],
        }

    def build_channels(self, agent, requested_names: list[str] | None = None):
        channel_names = list(dict.fromkeys(self.enabled_names(category="channel") + (requested_names or [])))
        channels = []
        for name in channel_names:
            manifest = self.require(name)
            status = self.status(name)
            if not status.available:
                raise RuntimeError(
                    f"Extension `{name}` is not ready. "
                    f"Missing env: {status.missing_env or 'none'}; "
                    f"missing modules: {status.missing_modules or 'none'}"
                )
            if not manifest.factory_path:
                continue
            factory = self._resolve_factory(manifest.factory_path)
            channels.append(factory(agent))
        return channels

    @staticmethod
    def _resolve_factory(path: str):
        module_name, attr_name = path.split(":", 1)
        module = import_module(module_name)
        return getattr(module, attr_name)

