from __future__ import annotations

from pathlib import Path
import re

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


def _provider_recovery_hint(provider: str, state: dict) -> str:
    if state.get("llm_usable"):
        return ""
    auth_mode = state.get("auth_mode")
    env_name = state.get("env_name")
    if state.get("configured"):
        if provider == "openai" and state.get("source") == "openai_codex_oauth":
            return "Codex OAuth is configured for the Codex adapter, not the OpenAI SDK; use `helloagi models set-provider codex` or set OPENAI_API_KEY."
        if auth_mode == "api_key" and env_name:
            return f"Configured credential is not usable for the LLM backbone; set a real {env_name} or choose another provider."
        return "Configured credential is not usable for the LLM backbone; refresh it or choose another provider."
    if provider == "anthropic":
        return "Set ANTHROPIC_API_KEY or activate an Anthropic auth profile."
    if provider == "google":
        return "Set GOOGLE_API_KEY or activate a Google auth profile."
    if provider == "openai":
        return "Set OPENAI_API_KEY, run `helloagi auth login-openai`, or select the Codex adapter if using Codex OAuth."
    return "Configure provider credentials, then rerun `helloagi health`."


def _build_provider_health(providers: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    provider_health: dict[str, dict[str, object]] = {}
    for provider, state in providers.items():
        provider_health[provider] = {
            "configured": bool(state.get("configured")),
            "usable": bool(state.get("llm_usable")),
            "auth_mode": state.get("auth_mode", "none"),
            "source": state.get("source", "none"),
            "env_name": state.get("env_name"),
            "profile_name": state.get("profile_name"),
            "secret_present": bool(state.get("configured")),
            "recovery_hint": _provider_recovery_hint(provider, state),
        }
    return provider_health


def _build_channel_health(extension_manager: ExtensionManager) -> dict[str, dict[str, object]]:
    channel_health: dict[str, dict[str, object]] = {}
    for status in extension_manager.list_extensions(category="channel"):
        recovery_hint = extension_manager.readiness_hint(status.name, status=status) if not status.available else ""
        channel_health[status.name] = {
            "enabled": status.enabled,
            "available": status.available,
            "missing_env": list(status.missing_env),
            "missing_modules": list(status.missing_modules),
            "recovery_hint": recovery_hint,
        }
    return channel_health


def _build_service_recovery(service_manager: ServiceManager) -> dict[str, object]:
    doctor = service_manager.doctor()

    def redact(value: object) -> str:
        text = str(value)
        # Health output is user-facing and may be copied into bug reports; keep
        # recovery actions but remove machine-specific absolute paths. Handle
        # quoted/backticked paths and parenthesized interpreter paths first so
        # paths with spaces do not leak suffixes.
        text = re.sub(r"`[^`]*(?:/|\\)[^`]*`", "`<path>`", text)
        text = re.sub(r"\"[^\"]*(?:/|\\)[^\"]*\"", '"<path>"', text)
        text = re.sub(r"'[^']*(?:/|\\)[^']*'", "'<path>'", text)
        text = re.sub(r"\([^)]*(?:/|\\)[^)]*\)", "(<path>)", text)
        text = re.sub(r"(?<!\w)(?:[A-Za-z]:\\|/)[^\s`)]+", "<path>", text)
        return text

    return {
        "ok": bool(doctor.get("ok")),
        "installed": bool(doctor.get("installed")),
        "issues": [redact(item) for item in doctor.get("issues", [])],
        "recommendations": [redact(item) for item in doctor.get("recommendations", [])],
        "notes": [redact(item) for item in doctor.get("notes", [])],
        "backend": doctor.get("backend", "none"),
    }


def format_health_report(report: dict) -> str:
    lines = ["HelloAGI organism health:"]
    for organ, state in report.get("organ_health", {}).items():
        lines.append(f"- {organ}: {state['status']} — {state['summary']}")
        if state.get("recommendation"):
            lines.append(f"  next: {state['recommendation']}")
    provider_health = report.get("provider_health", {})
    if provider_health:
        lines.append("provider_status:")
        for provider, state in provider_health.items():
            configured = "configured" if state.get("configured") else "not configured"
            usable = "usable" if state.get("usable") else "not usable"
            auth_mode = state.get("auth_mode") or "none"
            source = state.get("source") or "none"
            lines.append(f"- {provider}: {configured} / {usable} (auth_mode={auth_mode}, source={source})")
            if state.get("recovery_hint"):
                lines.append(f"  next: {state['recovery_hint']}")
    service_recovery = report.get("service_recovery", {})
    if service_recovery:
        service_state = "ok" if service_recovery.get("ok") else "needs attention"
        issues = ", ".join(service_recovery.get("issues", [])) or "none"
        lines.append(f"service_recovery: {service_state} (issues={issues})")
        for recommendation in service_recovery.get("recommendations", []):
            lines.append(f"  next: {recommendation}")
        for note in service_recovery.get("notes", []):
            lines.append(f"  note: {note}")
    channel_health = report.get("channel_health", {})
    if channel_health:
        lines.append("channel_status:")
        for channel, state in channel_health.items():
            enabled = "enabled" if state.get("enabled") else "not enabled"
            available = "available" if state.get("available") else "not available"
            lines.append(f"- {channel}: {enabled} / {available}")
            if state.get("missing_env"):
                lines.append(f"  missing_env: {', '.join(state['missing_env'])}")
            if state.get("missing_modules"):
                lines.append(f"  missing_modules: {', '.join(state['missing_modules'])}")
            if state.get("recovery_hint"):
                lines.append(f"  next: {state['recovery_hint']}")
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
    service_manager = ServiceManager()
    extension_manager = ExtensionManager()
    service = service_manager.status()
    extensions = extension_manager.doctor()
    auth_profiles = AuthProfileManager(path=auth_profiles_path, env_path=env_path).doctor()
    providers = provider_env_snapshot(env_path=env_path, auth_profiles_path=auth_profiles_path)
    telegram_status = extension_manager.status("telegram")
    discord_status = extension_manager.status("discord")
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
    provider_health = _build_provider_health(providers)
    service_recovery = _build_service_recovery(service_manager)
    channel_health = _build_channel_health(extension_manager)
    return {
        "ok": overall_ok,
        "checks": checks,
        "organ_health": organ_health,
        "provider_health": provider_health,
        "service_recovery": service_recovery,
        "channel_health": channel_health,
        "safe_mode": _safe_mode_from_organs(organ_health),
        "scorecard": scorecard,
        "service": service,
        "extensions": extensions,
        "auth_profiles": auth_profiles,
        "providers": providers,
    }
