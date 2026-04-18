from __future__ import annotations

from pathlib import Path
import os

from agi_runtime.config.settings import load_settings
from agi_runtime.diagnostics.scorecard import run_scorecard
from agi_runtime.extensions.manager import ExtensionManager
from agi_runtime.service.manager import ServiceManager


def run_health(config_path: str = "helloagi.json", onboard_path: str = "helloagi.onboard.json") -> dict:
    settings = load_settings(config_path)
    scorecard = run_scorecard(config_path=config_path, onboard_path=onboard_path)
    service = ServiceManager().status()
    extensions = ExtensionManager().doctor()
    checks = {
        "config_exists": Path(config_path).exists(),
        "onboard_exists": Path(onboard_path).exists(),
        "db_exists": Path(settings.db_path).exists(),
        "journal_exists": Path(settings.journal_path).exists(),
        "anthropic_ready": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "telegram_ready": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "discord_ready": bool(os.environ.get("DISCORD_BOT_TOKEN")),
        "service_auth_ready": bool(os.environ.get("HELLOAGI_API_KEY")),
        "service_installed": service["installed"],
        "service_running": service["running"],
        "extensions_ready": all(item["available"] for item in extensions["extensions"] if item["enabled"]),
    }
    overall_ok = scorecard["grade"] >= 60 and not any(
        value is False for key, value in checks.items() if key in {"config_exists", "db_exists", "journal_exists"}
    )
    return {
        "ok": overall_ok,
        "checks": checks,
        "scorecard": scorecard,
        "service": service,
        "extensions": extensions,
    }
