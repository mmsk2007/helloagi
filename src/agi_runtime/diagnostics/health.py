from __future__ import annotations

from pathlib import Path

from agi_runtime.auth.profiles import AuthProfileManager
from agi_runtime.config.env import resolve_env_value
from agi_runtime.config.providers import provider_env_snapshot
from agi_runtime.config.settings import load_settings
from agi_runtime.diagnostics.scorecard import run_scorecard
from agi_runtime.extensions.manager import ExtensionManager
from agi_runtime.service.manager import ServiceManager


def run_health(config_path: str = "helloagi.json", onboard_path: str = "helloagi.onboard.json") -> dict:
    settings = load_settings(config_path)
    runtime_root = Path(config_path).resolve().parent
    env_path = str(runtime_root / ".env")
    auth_profiles_path = str(runtime_root / "memory" / "auth_profiles.json")
    scorecard = run_scorecard(config_path=config_path, onboard_path=onboard_path)
    service = ServiceManager().status()
    extensions = ExtensionManager().doctor()
    auth_profiles = AuthProfileManager(path=auth_profiles_path, env_path=env_path).doctor()
    providers = provider_env_snapshot(env_path=env_path, auth_profiles_path=auth_profiles_path)
    telegram_status = ExtensionManager().status("telegram")
    discord_status = ExtensionManager().status("discord")
    checks = {
        "config_exists": Path(config_path).exists(),
        "onboard_exists": Path(onboard_path).exists(),
        "db_exists": Path(settings.db_path).exists(),
        "journal_exists": Path(settings.journal_path).exists(),
        "anthropic_ready": bool(providers.get("anthropic", {}).get("configured")),
        "google_ready": bool(providers.get("google", {}).get("configured")),
        "openai_ready": bool(providers.get("openai", {}).get("configured")),
        "telegram_ready": telegram_status.available,
        "discord_ready": discord_status.available,
        "service_auth_ready": bool(resolve_env_value("HELLOAGI_API_KEY", env_path)),
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
        "auth_profiles": auth_profiles,
        "providers": providers,
    }
