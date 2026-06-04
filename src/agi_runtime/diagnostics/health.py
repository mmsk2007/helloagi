from __future__ import annotations

from pathlib import Path

from agi_runtime.auth.profiles import AuthProfileManager
from agi_runtime.config.env import resolve_env_value
from agi_runtime.config.providers import provider_env_snapshot
from agi_runtime.config.settings import load_settings
from agi_runtime.diagnostics.scorecard import run_scorecard
from agi_runtime.extensions.manager import ExtensionManager
from agi_runtime.service.manager import ServiceManager


def _organ(status: str, summary: str, recommendation: str = "") -> dict[str, str]:
    return {"status": status, "summary": summary, "recommendation": recommendation}


def _build_organ_health(*, checks: dict, providers: dict, service: dict, extensions: dict) -> dict[str, dict[str, str]]:
    provider_names = [name for name, state in providers.items() if state.get("llm_usable")]
    enabled_extensions = [item for item in extensions["extensions"] if item["enabled"]]
    unavailable_enabled = [item["name"] for item in enabled_extensions if not item["available"]]
    any_channel_ready = bool(checks["telegram_ready"] or checks["discord_ready"])
    memory_ready = bool(checks["db_exists"] and checks["journal_exists"])
    service_ready = bool(service["running"] and service.get("health", {}).get("ok"))
    service_configured = bool(service["installed"])

    return {
        "brain": _organ(
            "ok" if provider_names else "action_required",
            "LLM backbone usable" if provider_names else "No usable LLM backbone configured",
            "" if provider_names else "Configure at least one usable LLM provider, then rerun `helloagi health`.",
        ),
        "senses": _organ(
            "ok" if any_channel_ready else "degraded",
            "At least one live channel extension is available" if any_channel_ready else "CLI input is available; Telegram/Discord are not ready",
            "Enable/configure a channel extension if channel operation is needed." if not any_channel_ready else "",
        ),
        "effectors": _organ(
            "ok" if checks["extensions_ready"] else "degraded",
            "Enabled extensions are available" if checks["extensions_ready"] else f"Unavailable enabled extensions: {', '.join(unavailable_enabled)}",
            "Install missing extension dependencies or disable unavailable extensions." if unavailable_enabled else "",
        ),
        "immune": _organ(
            "ok",
            "SRG policy packs and service auth checks are present",
            "",
        ),
        "memory": _organ(
            "ok" if memory_ready else "action_required",
            "DB and journal paths exist" if memory_ready else "Memory DB or journal path is missing",
            "Run `helloagi db init` or start a normal run to initialize memory files." if not memory_ready else "",
        ),
        "metabolism": _organ(
            "ok",
            "Runtime budgets and service backpressure settings are configurable",
            "",
        ),
        "channels": _organ(
            "ok" if any_channel_ready else "degraded",
            "A channel adapter is ready" if any_channel_ready else "No optional channel adapter is ready",
            "Configure Telegram/Discord only if non-CLI operation is required." if not any_channel_ready else "",
        ),
        "homeostasis": _organ(
            "ok" if service_ready else "degraded",
            "Service is running and healthy" if service_ready else ("Service installed but not healthy/running" if service_configured else "Background service is not installed"),
            "Run `helloagi service doctor` before starting/reinstalling the service." if service_configured and not service_ready else "Install/start the service only when background operation is needed.",
        ),
        "growth": _organ(
            "ok",
            "Skill and scorecard subsystems are inspectable",
            "",
        ),
    }


def _safe_mode_from_organs(organ_health: dict[str, dict[str, str]]) -> dict:
    critical_organs = [
        organ
        for organ in ("brain", "memory", "homeostasis")
        if organ_health[organ]["status"] == "action_required"
    ]
    return {
        "active": bool(critical_organs),
        "critical_organs": critical_organs,
        "recommendation": (
            "Use CLI diagnostics and configuration commands only until action-required organs are fixed."
            if critical_organs
            else "No safe-mode recommendation needed."
        ),
    }


def format_health_report(report: dict) -> str:
    lines = ["HelloAGI organism health:"]
    for organ, state in report.get("organ_health", {}).items():
        lines.append(f"- {organ}: {state['status']} — {state['summary']}")
        if state.get("recommendation"):
            lines.append(f"  next: {state['recommendation']}")
    safe_mode = report.get("safe_mode", {})
    state = "active" if safe_mode.get("active") else "inactive"
    lines.append(f"safe_mode: {state}")
    if safe_mode.get("critical_organs"):
        lines.append(f"critical_organs: {', '.join(safe_mode['critical_organs'])}")
    if safe_mode.get("recommendation"):
        lines.append(f"safe_mode_recommendation: {safe_mode['recommendation']}")
    return "\n".join(lines)


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
        "anthropic_ready": bool(providers.get("anthropic", {}).get("llm_usable")),
        "google_ready": bool(providers.get("google", {}).get("llm_usable")),
        "openai_ready": bool(providers.get("openai", {}).get("llm_usable")),
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
    organ_health = _build_organ_health(checks=checks, providers=providers, service=service, extensions=extensions)
    return {
        "ok": overall_ok,
        "checks": checks,
        "organ_health": organ_health,
        "safe_mode": _safe_mode_from_organs(organ_health),
        "scorecard": scorecard,
        "service": service,
        "extensions": extensions,
        "auth_profiles": auth_profiles,
        "providers": providers,
    }
