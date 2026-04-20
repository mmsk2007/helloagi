from __future__ import annotations

from dataclasses import asdict, dataclass, field
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
import json
import os
import re
from typing import Any

from agi_runtime.config.env import load_local_env


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


def _build_voice_channel(agent):
    from agi_runtime.channels.voice import VoiceChannel

    return VoiceChannel(agent)


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
                    name="voice",
                    title="Local Voice",
                    category="channel",
                    description="Wake-word local microphone + speaker channel for hands-free desktop conversations.",
                    python_modules=[],
                    extras=["helloagi[voice]"],
                    factory_path="agi_runtime.extensions.manager:_build_voice_channel",
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
        missing_modules = []
        for module_name in manifest.python_modules:
            try:
                if find_spec(module_name) is None:
                    missing_modules.append(module_name)
            except ModuleNotFoundError:
                missing_modules.append(module_name)
        notes: list[str] = []
        if manifest.name == "voice":
            from agi_runtime.channels.voice import probe_voice_runtime

            voice_probe = probe_voice_runtime()
            missing_modules = list(voice_probe.get("missing_modules", []))
            notes.extend(str(note) for note in voice_probe.get("notes", []))
        available = not missing_env and not missing_modules
        if missing_env:
            notes.append(f"Set: {', '.join(missing_env)}")
        if missing_modules:
            notes.append("Install extra: " + ", ".join(manifest.extras or manifest.python_modules))
            notes.append(f"Run: {self.install_command(manifest.name)}")
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

    def resolve_channel_names(
        self,
        *,
        requested_names: list[str] | None = None,
        include_enabled: bool = True,
    ) -> list[str]:
        requested = [name for name in (requested_names or []) if name in self._manifests]
        if include_enabled:
            enabled = self.enabled_names(category="channel")
            return list(dict.fromkeys(enabled + requested))
        return list(dict.fromkeys(requested))

    def build_channels(
        self,
        agent,
        requested_names: list[str] | None = None,
        *,
        include_enabled: bool = True,
    ):
        channel_names = self.resolve_channel_names(requested_names=requested_names, include_enabled=include_enabled)
        channels = []
        for name in channel_names:
            manifest = self.require(name)
            status = self.status(name)
            if not status.available:
                remediation = self.readiness_hint(name, status=status)
                raise RuntimeError(
                    f"Extension `{name}` is not ready. "
                    f"Missing env: {status.missing_env or 'none'}; "
                    f"missing modules: {status.missing_modules or 'none'}. "
                    f"{remediation}"
                )
            if not manifest.factory_path:
                continue
            factory = self._resolve_factory(manifest.factory_path)
            channels.append(factory(agent))
        return channels

    def install_command(self, name: str) -> str:
        self.require(name)
        return f"python -m agi_runtime.cli extensions install {name}"

    def readiness_hint(self, name: str, *, status: ExtensionStatus | None = None) -> str:
        manifest = self.require(name)
        status = status or self.status(name)
        hints: list[str] = []
        if status.missing_modules:
            hints.append(f"Run: {self.install_command(manifest.name)}")
        if status.missing_env:
            hints.append(f"Set env: {', '.join(status.missing_env)}")
        return " ".join(hints) or f"Inspect with: python -m agi_runtime.cli extensions info {manifest.name}"

    def install_plan(self, name: str) -> tuple[list[str], Path | None]:
        manifest = self.require(name)
        if not manifest.extras:
            raise RuntimeError(f"Extension `{name}` has no installable extra.")
        project_root = self._find_local_project_root()
        if project_root is not None:
            extra_suffix = self._local_extra_suffix(manifest.extras[0])
            return ["install", "-e", f".[{extra_suffix}]"], project_root
        return ["install", manifest.extras[0]], None

    @staticmethod
    def _resolve_factory(path: str):
        module_name, attr_name = path.split(":", 1)
        module = import_module(module_name)
        return getattr(module, attr_name)

    @staticmethod
    def _find_local_project_root() -> Path | None:
        current = Path(__file__).resolve()
        for candidate in current.parents:
            if (candidate / "pyproject.toml").exists() and (candidate / "src" / "agi_runtime").exists():
                return candidate
        return None

    @staticmethod
    def _local_extra_suffix(extra_spec: str) -> str:
        match = re.search(r"\[([^\]]+)\]$", extra_spec)
        if not match:
            raise RuntimeError(f"Unsupported extension extra spec: {extra_spec}")
        return match.group(1)
