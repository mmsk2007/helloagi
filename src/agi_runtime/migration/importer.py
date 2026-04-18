from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import os
from typing import Any

from agi_runtime.config.env import save_env_values


@dataclass
class ImportReport:
    source: str
    source_path: str
    found: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    applied: bool = False


class MigrationImporter:
    ENV_KEYS = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "TELEGRAM_BOT_TOKEN",
    ]

    DEFAULT_PATHS = {
        "openclaw": Path.home() / ".openclaw",
        "hermes": Path.home() / ".hermes",
    }

    def preview(self, source: str, path: str | None = None) -> ImportReport:
        source_path = Path(path) if path else self.DEFAULT_PATHS[source]
        report = ImportReport(source=source, source_path=str(source_path))
        if not source_path.exists():
            report.notes.append("Source path does not exist.")
            report.missing.extend(self.ENV_KEYS)
            return report

        env_values = self._load_env_file(source_path / ".env")
        found = {key: env_values[key] for key in self.ENV_KEYS if env_values.get(key)}

        if source == "openclaw":
            json_values = self._load_openclaw_json(source_path)
            for key, value in json_values.items():
                found.setdefault(key, value)

        report.found = {key: self._redact(value) for key, value in found.items()}
        report.missing = [key for key in self.ENV_KEYS if key not in found]
        if found:
            report.notes.append(f"Ready to import {len(found)} secret(s) into local .env")
        return report

    def apply(self, source: str, path: str | None = None) -> ImportReport:
        report = self.preview(source, path)
        source_path = Path(report.source_path)
        env_values = self._load_env_file(source_path / ".env")
        found = {key: env_values[key] for key in self.ENV_KEYS if env_values.get(key)}
        if source == "openclaw":
            found.update({k: v for k, v in self._load_openclaw_json(source_path).items() if v})
        save_env_values(found)
        for key, value in found.items():
            os.environ.setdefault(key, value)
        report.applied = bool(found)
        if report.applied:
            report.notes.append("Imported secrets into local .env")
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

    def _load_openclaw_json(self, root: Path) -> dict[str, str]:
        candidates = [root / "openclaw.json", root / "config.json"]
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            found: dict[str, str] = {}
            anthropic = self._deep_get(data, ["models", "providers", "anthropic", "apiKey"])
            openai = self._deep_get(data, ["models", "providers", "openai", "apiKey"])
            google = self._deep_get(data, ["models", "providers", "google", "apiKey"])
            telegram = self._deep_get(data, ["channels", "telegram", "botToken"])
            if isinstance(anthropic, str) and anthropic:
                found["ANTHROPIC_API_KEY"] = anthropic
            if isinstance(openai, str) and openai:
                found["OPENAI_API_KEY"] = openai
            if isinstance(google, str) and google:
                found["GOOGLE_API_KEY"] = google
            if isinstance(telegram, str) and telegram:
                found["TELEGRAM_BOT_TOKEN"] = telegram
            accounts = self._deep_get(data, ["channels", "telegram", "accounts", "default", "botToken"])
            if isinstance(accounts, str) and accounts:
                found.setdefault("TELEGRAM_BOT_TOKEN", accounts)
            return found
        return {}

    @staticmethod
    def _deep_get(data: dict[str, Any], path: list[str]) -> Any:
        cur: Any = data
        for key in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    @staticmethod
    def _redact(value: str) -> str:
        if len(value) <= 8:
            return "*" * len(value)
        return value[:4] + "*" * max(4, len(value) - 8) + value[-4:]
