from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import os
import shutil
from typing import Any

from agi_runtime.config.env import save_env_values


@dataclass
class ImportReport:
    source: str
    source_path: str
    secrets_found: dict[str, str] = field(default_factory=dict)
    config_found: dict[str, Any] = field(default_factory=dict)
    channels_found: dict[str, Any] = field(default_factory=dict)
    workspace_files: list[str] = field(default_factory=list)
    skill_files: list[str] = field(default_factory=list)
    approval_files: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    destination_artifacts: list[str] = field(default_factory=list)
    applied: bool = False


class MigrationImporter:
    ENV_KEYS = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
    ]

    DEFAULT_PATHS = {
        "openclaw": Path.home() / ".openclaw",
        "hermes": Path.home() / ".hermes",
    }

    def __init__(self, import_root: str = "memory/imports", skills_dir: str = "memory/skills"):
        self.import_root = Path(import_root)
        self.skills_dir = Path(skills_dir)
        self.import_root.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def preview(self, source: str, path: str | None = None) -> ImportReport:
        source_path = Path(path) if path else self.DEFAULT_PATHS[source]
        report = ImportReport(source=source, source_path=str(source_path))
        if not source_path.exists():
            report.notes.append("Source path does not exist.")
            report.missing.extend(self.ENV_KEYS)
            return report

        env_values = self._load_env_file(source_path / ".env")
        found = {key: env_values[key] for key in self.ENV_KEYS if env_values.get(key)}
        cfg = self._load_source_config(source, source_path)
        found.update({key: value for key, value in cfg.get("secrets", {}).items() if value})

        report.secrets_found = {key: self._redact(value) for key, value in found.items()}
        report.config_found = cfg.get("config", {})
        report.channels_found = cfg.get("channels", {})
        report.workspace_files = [str(path) for path in self._workspace_candidates(source, source_path)]
        report.skill_files = [str(path) for path in self._skill_candidates(source, source_path)]
        report.approval_files = [str(path) for path in self._approval_candidates(source, source_path)]
        report.missing = [key for key in self.ENV_KEYS if key not in found]
        if found:
            report.notes.append(f"Ready to import {len(found)} secret(s) into local .env")
        if report.workspace_files:
            report.notes.append(f"Workspace memory files detected: {len(report.workspace_files)}")
        if report.skill_files:
            report.notes.append(f"Skills detected: {len(report.skill_files)}")
        if report.approval_files:
            report.notes.append(f"Approval files detected: {len(report.approval_files)}")
        return report

    def apply(
        self,
        source: str,
        path: str | None = None,
        *,
        overwrite: bool = False,
        rename_imports: bool = False,
    ) -> ImportReport:
        report = self.preview(source, path)
        source_path = Path(report.source_path)
        if not source_path.exists():
            return report

        cfg = self._load_source_config(source, source_path)
        env_values = self._load_env_file(source_path / ".env")
        found = {key: env_values[key] for key in self.ENV_KEYS if env_values.get(key)}
        found.update({key: value for key, value in cfg.get("secrets", {}).items() if value})

        if found:
            save_env_values(found)
            for key, value in found.items():
                os.environ.setdefault(key, value)

        self._update_onboarding_state(found)

        source_import_root = self.import_root / source
        artifacts: list[str] = []
        conflicts: list[str] = []

        for src in self._workspace_candidates(source, source_path):
            dest = self._resolve_destination(source_import_root / "workspace" / src.name, overwrite=overwrite, rename_imports=rename_imports)
            if dest is None:
                conflicts.append(str(src))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            artifacts.append(str(dest))

        for src in self._approval_candidates(source, source_path):
            dest = self._resolve_destination(source_import_root / "approvals" / src.name, overwrite=overwrite, rename_imports=rename_imports)
            if dest is None:
                conflicts.append(str(src))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            artifacts.append(str(dest))

        for src in self._skill_candidates(source, source_path):
            dest_name = f"{source}-{src.stem}.md"
            dest = self._resolve_destination(self.skills_dir / dest_name, overwrite=overwrite, rename_imports=rename_imports)
            if dest is None:
                conflicts.append(str(src))
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = src.read_text(encoding="utf-8")
            if not content.lstrip().startswith("---"):
                content = self._wrap_skill_markdown(source, src.stem, content)
            dest.write_text(content, encoding="utf-8")
            artifacts.append(str(dest))

        summary_path = source_import_root / "migration_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "source": source,
            "source_path": report.source_path,
            "config_found": report.config_found,
            "channels_found": report.channels_found,
            "artifacts": artifacts,
            "conflicts": conflicts,
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        artifacts.append(str(summary_path))

        report.conflicts = conflicts
        report.destination_artifacts = artifacts
        report.applied = bool(found or artifacts)
        if report.applied:
            report.notes.append("Imported secrets and copied source artifacts into HelloAGI state.")
        return report

    def _load_env_file(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        out: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip("'").strip('"')
        return out

    def _load_source_config(self, source: str, root: Path) -> dict[str, Any]:
        if source == "openclaw":
            return self._load_openclaw_config(root)
        return self._load_hermes_config(root)

    def _load_openclaw_config(self, root: Path) -> dict[str, Any]:
        candidates = [root / "openclaw.json", root / "config.json"]
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            secrets: dict[str, str] = {}
            channels: dict[str, Any] = {}
            config: dict[str, Any] = {}

            anthropic = self._deep_get(data, ["models", "providers", "anthropic", "apiKey"])
            openai = self._deep_get(data, ["models", "providers", "openai", "apiKey"])
            google = self._deep_get(data, ["models", "providers", "google", "apiKey"])
            telegram = self._deep_get(data, ["channels", "telegram", "botToken"])
            discord = self._deep_get(data, ["channels", "discord", "token"])
            workspace = self._deep_get(data, ["workspace", "path"])
            dm_policy = self._deep_get(data, ["channels", "telegram", "dmPolicy"])
            allow_from = self._deep_get(data, ["channels", "telegram", "allowFrom"])

            if isinstance(anthropic, str) and anthropic:
                secrets["ANTHROPIC_API_KEY"] = anthropic
            if isinstance(openai, str) and openai:
                secrets["OPENAI_API_KEY"] = openai
            if isinstance(google, str) and google:
                secrets["GOOGLE_API_KEY"] = google
            if isinstance(telegram, str) and telegram:
                secrets["TELEGRAM_BOT_TOKEN"] = telegram
                channels["telegram"] = {"configured": True}
            if isinstance(discord, str) and discord:
                secrets["DISCORD_BOT_TOKEN"] = discord
                channels["discord"] = {"configured": True}
            if isinstance(workspace, str) and workspace:
                config["workspace_path"] = workspace
            if dm_policy is not None:
                config["telegram_dm_policy"] = dm_policy
            if allow_from is not None:
                channels.setdefault("telegram", {})["allow_from"] = allow_from

            return {"secrets": secrets, "config": config, "channels": channels}
        return {"secrets": {}, "config": {}, "channels": {}}

    def _load_hermes_config(self, root: Path) -> dict[str, Any]:
        secrets: dict[str, str] = {}
        config: dict[str, Any] = {}
        channels: dict[str, Any] = {}

        env_values = self._load_env_file(root / ".env")
        for key in self.ENV_KEYS:
            if env_values.get(key):
                secrets[key] = env_values[key]

        config_candidates = [
            root / "config.json",
            root / "gateway.json",
            root / "settings.json",
        ]
        for candidate in config_candidates:
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            telegram = self._deep_find_key(data, "telegram")
            discord = self._deep_find_key(data, "discord")
            workspace = self._deep_find_key(data, "workspace")
            if telegram is not None:
                channels["telegram"] = {"configured": True}
            if discord is not None:
                channels["discord"] = {"configured": True}
            if isinstance(workspace, str):
                config["workspace_path"] = workspace
            break

        return {"secrets": secrets, "config": config, "channels": channels}

    def _workspace_candidates(self, source: str, root: Path) -> list[Path]:
        names = ["AGENTS.md", "BOOTSTRAP.md", "HEARTBEAT.md", "IDENTITY.md", "SOUL.md", "TOOLS.md", "USER.md", "MEMORY.md"]
        candidates: list[Path] = []
        base_dirs = [root, root / "workspace"]
        for base in base_dirs:
            for name in names:
                path = base / name
                if path.exists():
                    candidates.append(path)
        return self._dedupe(candidates)

    def _skill_candidates(self, source: str, root: Path) -> list[Path]:
        candidates: list[Path] = []
        for rel in ["skills", "workspace/skills", "optional-skills"]:
            base = root / rel
            if base.exists():
                candidates.extend(base.rglob("*.md"))
        return self._dedupe(candidates)

    def _approval_candidates(self, source: str, root: Path) -> list[Path]:
        candidates: list[Path] = []
        explicit = [
            root / "exec-approvals.json",
            root / "allowlist.json",
            root / "approval-allowlist.json",
        ]
        candidates.extend([path for path in explicit if path.exists()])
        agents_root = root / "agents"
        if agents_root.exists():
            candidates.extend(agents_root.rglob("auth-profiles.json"))
        return self._dedupe(candidates)

    def _update_onboarding_state(self, found: dict[str, str], onboard_path: str = "helloagi.onboard.json"):
        path = Path(onboard_path)
        data: dict[str, Any] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        providers = data.setdefault("providers", {})
        channels = data.setdefault("channels", {})
        if found.get("ANTHROPIC_API_KEY"):
            providers["anthropic_api_key"] = True
        if found.get("OPENAI_API_KEY"):
            providers["openai_api_key"] = True
        if found.get("GOOGLE_API_KEY"):
            providers["google_api_key"] = True
        if found.get("TELEGRAM_BOT_TOKEN"):
            channels["telegram_bot_token"] = True
        if found.get("DISCORD_BOT_TOKEN"):
            channels["discord_bot_token"] = True
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _resolve_destination(self, path: Path, *, overwrite: bool, rename_imports: bool) -> Path | None:
        if overwrite or not path.exists():
            return path
        if not rename_imports:
            return None
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _wrap_skill_markdown(source: str, name: str, content: str) -> str:
        return (
            "---\n"
            f"name: {source}-{name}\n"
            f"description: Imported from {source}\n"
            "triggers: []\n"
            "tools: []\n"
            "created_at: 0\n"
            "invoke_count: 0\n"
            "---\n\n"
            f"{content.strip()}\n"
        )

    @staticmethod
    def _deep_get(data: dict[str, Any], path: list[str]) -> Any:
        cur: Any = data
        for key in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    @classmethod
    def _deep_find_key(cls, data: Any, needle: str) -> Any:
        if isinstance(data, dict):
            for key, value in data.items():
                if key == needle:
                    return value
                nested = cls._deep_find_key(value, needle)
                if nested is not None:
                    return nested
        elif isinstance(data, list):
            for item in data:
                nested = cls._deep_find_key(item, needle)
                if nested is not None:
                    return nested
        return None

    @staticmethod
    def _redact(value: str) -> str:
        if len(value) <= 8:
            return "*" * len(value)
        return value[:4] + "*" * max(4, len(value) - 8) + value[-4:]

    @staticmethod
    def _dedupe(paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        out: list[Path] = []
        for path in paths:
            resolved = str(path)
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(path)
        return out
