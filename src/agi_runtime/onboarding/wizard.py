"""HelloAGI onboarding wizard.

This is the product setup flow for install-to-first-chat:
- detect the current environment
- optionally import from OpenClaw/Hermes
- choose the active runtime/provider profile
- configure channels and service auth
- run a quick readiness check
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import os
import platform
import shutil
import sys

from agi_runtime.auth.profiles import AuthProfileManager
from agi_runtime.channels.voice import probe_voice_runtime
from agi_runtime.config.env import load_local_env, save_env_values
from agi_runtime.config.providers import provider_env_snapshot, resolve_provider_credential
from agi_runtime.config.settings import RuntimeSettings, load_settings, save_settings
from agi_runtime.extensions.manager import ExtensionManager
from agi_runtime.migration.importer import MigrationImporter
from agi_runtime.service.manager import ServiceManager


BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
NC = "\033[0m"

if not sys.stdout.isatty():
    BOLD = DIM = CYAN = GREEN = YELLOW = RED = MAGENTA = BLUE = NC = ""


PROVIDER_PROMPTS: dict[str, dict[str, str]] = {
    "anthropic": {
        "api_key": "ANTHROPIC_API_KEY",
        "auth_token": "ANTHROPIC_AUTH_TOKEN",
    },
    "google": {
        "api_key": "GOOGLE_API_KEY",
        "auth_token": "GOOGLE_AUTH_TOKEN",
    },
    "openai": {
        "api_key": "OPENAI_API_KEY",
        "auth_token": "OPENAI_AUTH_TOKEN",
    },
}


@dataclass
class ProviderKeys:
    active_provider: str = "template"
    active_auth_mode: str = "none"
    active_profile: str = ""
    openai_api_key: bool = False
    openai_auth_token: bool = False
    anthropic_api_key: bool = False
    anthropic_auth_token: bool = False
    google_api_key: bool = False
    google_auth_token: bool = False


@dataclass
class ChannelKeys:
    telegram_bot_token: bool = False
    telegram_enabled: bool = False
    discord_bot_token: bool = False
    discord_enabled: bool = False
    voice_enabled: bool = False


@dataclass
class ServiceSetup:
    runtime_mode: str = "hybrid"
    auth_token: bool = False
    background_service: bool = False
    backend: str = "process"
    host: str = "127.0.0.1"
    port: int = 8787


@dataclass
class OnboardConfig:
    version: int = 2
    agent_name: str = "HelloAGI"
    owner_name: str = ""
    timezone: str = "UTC"
    default_model_tier: str = "balanced"
    focus: str = "general"
    providers: ProviderKeys = field(default_factory=ProviderKeys)
    channels: ChannelKeys = field(default_factory=ChannelKeys)
    service: ServiceSetup = field(default_factory=ServiceSetup)
    extensions_enabled: list[str] = field(default_factory=list)
    migration_source: str = ""
    env_detected: dict = field(default_factory=dict)
    setup_complete: bool = False


@dataclass
class WizardOptions:
    non_interactive: bool = False
    runtime_mode: str | None = None
    provider: str | None = None
    auth_mode: str | None = None
    service_auth_token: str | None = None
    enable_extensions: list[str] = field(default_factory=list)
    import_source: str | None = None
    agent_name: str | None = None
    owner_name: str | None = None
    focus: str | None = None
    model_tier: str | None = None
    timezone: str | None = None


def _to_dict(cfg: OnboardConfig) -> dict:
    return asdict(cfg)


def _write_private_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def _banner():
    from agi_runtime.onboarding.quotes import get_startup_quote

    quote = get_startup_quote()
    print()
    print(f"{BOLD}{CYAN}  HelloAGI{NC}  {DIM}v0.5.0{NC}")
    print()
    print(f"  {BOLD}The local-first governed agent runtime{NC}")
    print(f"  {DIM}Runtime setup, channels, service auth, and readiness in one flow{NC}")
    print()
    print(f"  {DIM}{MAGENTA}{quote}{NC}")
    print()


def _step(num: int, total: int, label: str):
    bar = f"{'#' * num}{'-' * (total - num)}"
    print(f"  {MAGENTA}[{bar}]{NC} {BOLD}Step {num}/{total}: {label}{NC}")


def _prompt(label: str, default: str = "") -> str:
    hint = f" {DIM}({default}){NC}" if default else ""
    try:
        value = input(f"    {CYAN}>{NC} {label}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return value or default


def _secret_prompt(label: str, default: str = "") -> str:
    hint = f" {DIM}(press Enter to keep current value){NC}" if default else f" {DIM}(press Enter to skip){NC}"
    try:
        value = input(f"    {CYAN}>{NC} {label}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return value or default


def _yes_no_prompt(label: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = _prompt(f"{label} [{hint}]", "")
    if not raw:
        return default
    return raw.strip().lower() in {"y", "yes", "1", "true"}


def _ok(message: str):
    print(f"    {GREEN}ok{NC} {message}")


def _warn(message: str):
    print(f"    {YELLOW}!{NC} {message}")


def _fail(message: str):
    print(f"    {RED}x{NC} {message}")


def _info(message: str):
    print(f"    {BLUE}i{NC} {message}")


def _detect_environment() -> dict:
    load_local_env()
    snapshot = provider_env_snapshot()
    env = {
        "os": platform.system(),
        "os_version": platform.version(),
        "python": platform.python_version(),
        "shell": os.environ.get("SHELL", os.environ.get("COMSPEC", "unknown")),
        "has_openclaw_home": (Path.home() / ".openclaw").exists(),
        "has_hermes_home": (Path.home() / ".hermes").exists(),
        "has_telegram_token": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "has_discord_token": bool(os.environ.get("DISCORD_BOT_TOKEN")),
        "has_service_auth_token": bool(os.environ.get("HELLOAGI_API_KEY")),
        "providers": snapshot,
    }
    for tool in ("git", "docker", "node", "pip"):
        env[f"has_{tool}"] = shutil.which(tool) is not None
    try:
        import telegram  # noqa: F401
        env["has_telegram_lib"] = True
    except ImportError:
        env["has_telegram_lib"] = False
    try:
        import discord  # noqa: F401
        env["has_discord_lib"] = True
    except ImportError:
        env["has_discord_lib"] = False
    voice_probe = probe_voice_runtime()
    env["has_voice_lib"] = bool(voice_probe.get("available"))
    env["voice_runtime_notes"] = list(voice_probe.get("notes", []))
    try:
        import rich  # noqa: F401
        env["has_rich"] = True
    except ImportError:
        env["has_rich"] = False
    return env


def _default_import_source(env: dict) -> str:
    if env.get("has_openclaw_home"):
        return "openclaw"
    if env.get("has_hermes_home"):
        return "hermes"
    return "skip"


def _maybe_import_existing_setup(env: dict) -> tuple[str, dict]:
    default_source = _default_import_source(env)
    if default_source == "skip":
        return "", env

    print()
    _info("Existing agent runtime detected.")
    if env.get("has_openclaw_home"):
        _info(f"OpenClaw source: {MigrationImporter.DEFAULT_PATHS['openclaw']}")
    if env.get("has_hermes_home"):
        _info(f"Hermes source: {MigrationImporter.DEFAULT_PATHS['hermes']}")
    choice = _prompt("Import before configuring? (openclaw/hermes/skip)", default_source).strip().lower()
    if choice not in {"openclaw", "hermes"}:
        return "", env

    importer = MigrationImporter()
    report = importer.preview(choice)
    print()
    _info(
        "Preview: "
        f"{len(report.secrets_found)} secrets, "
        f"{len(report.channels_found)} channels, "
        f"{len(report.workspace_files)} workspace files, "
        f"{len(report.skill_files)} skills."
    )
    if report.notes:
        for note in report.notes:
            _info(note)
    if not _yes_no_prompt(f"Apply {choice} import now", True):
        return "", env

    applied = importer.apply(choice, rename_imports=True)
    if applied.applied:
        _ok(f"Imported {choice} config and local artifacts into HelloAGI state.")
        return choice, _detect_environment()

    _warn(f"No importable state found in {applied.source_path}.")
    return "", env


def _provider_choice_default(env: dict) -> str:
    for provider in ("anthropic", "google"):
        if env["providers"].get(provider, {}).get("configured"):
            return provider
    return "template"


def _provider_choice_label(choice: str) -> str:
    return {
        "1": "template",
        "2": "anthropic",
        "3": "google",
    }.get(choice, choice)


def _provider_auth_default(provider: str, env: dict) -> str:
    detected = env["providers"].get(provider, {}).get("auth_mode")
    if detected in {"api_key", "auth_token"}:
        return detected
    return "api_key"


def _provider_prompt_name(provider: str, auth_mode: str) -> str:
    return PROVIDER_PROMPTS[provider][auth_mode]


def _normalize_runtime_mode(value: str | None, default: str = "hybrid") -> str:
    if value in {"cli", "hybrid", "service"}:
        return value
    return default


def _normalize_focus(value: str | None, default: str = "general") -> str:
    if value in {"general", "coding", "research", "creative"}:
        return value
    return default


def _normalize_model_tier(value: str | None, default: str = "balanced") -> str:
    if value in {"speed", "balanced", "quality"}:
        return value
    return default


def _normalize_provider(value: str | None, default: str = "template") -> str:
    if value in {"template", "anthropic", "google"}:
        return value
    return default


def _normalize_auth_mode(value: str | None, default: str = "api_key") -> str:
    if value in {"api_key", "auth_token"}:
        return value
    return default


def _default_profile_name(provider: str) -> str:
    return f"{provider}-default"


def _apply_import_source(choice: str) -> tuple[str, dict]:
    choice = (choice or "").strip().lower()
    if choice not in {"openclaw", "hermes"}:
        return "", _detect_environment()

    importer = MigrationImporter()
    report = importer.preview(choice)
    if report.notes:
        for note in report.notes:
            _info(note)
    applied = importer.apply(choice, rename_imports=True)
    if applied.applied:
        _ok(f"Imported {choice} config and local artifacts into HelloAGI state.")
        return choice, _detect_environment()

    _warn(f"No importable state found in {applied.source_path}.")
    return "", _detect_environment()


def _configure_primary_provider(
    provider: str,
    env: dict,
    *,
    auth_mode: str | None = None,
    non_interactive: bool = False,
) -> tuple[str, str, dict[str, str]]:
    if provider == "template":
        return "template", "none", {}

    chosen_auth_mode = _normalize_auth_mode(auth_mode, _provider_auth_default(provider, env))
    if not non_interactive:
        print()
        print(f"    {CYAN}1.{NC} API key")
        print(f"    {CYAN}2.{NC} Auth token")
        auth_choice = _prompt("Auth method (1-2)", "1" if chosen_auth_mode == "api_key" else "2")
        chosen_auth_mode = "auth_token" if auth_choice == "2" else "api_key"
    env_name = _provider_prompt_name(provider, chosen_auth_mode)
    existing = os.environ.get(env_name, "")
    if existing:
        _ok(f"{env_name} already present in environment")
        return provider, chosen_auth_mode, {}

    if non_interactive:
        _warn(f"{env_name} is not configured. HelloAGI will stay in template mode until you add one.")
        return "template", "none", {}

    secret = _secret_prompt(f"{env_name}")
    if not secret:
        _warn(f"No {provider} credential entered. HelloAGI will stay in template mode until you add one.")
        return "template", "none", {}
    return provider, chosen_auth_mode, {env_name: secret}


def _configure_optional_openai(env: dict, *, non_interactive: bool = False) -> tuple[str, dict[str, str]]:
    current = resolve_provider_credential("openai")
    if current.configured:
        _ok(f"Optional OpenAI credential detected via {current.env_name}")
        if non_interactive or not _yes_no_prompt("Replace the stored OpenAI credential", False):
            return current.auth_mode, {}

    if non_interactive:
        return current.auth_mode if current.configured else "none", {}

    if not _yes_no_prompt("Store an optional OpenAI credential for future adapters/tools", False):
        return current.auth_mode if current.configured else "none", {}

    print()
    print(f"    {CYAN}1.{NC} API key")
    print(f"    {CYAN}2.{NC} Auth token")
    auth_choice = _prompt("OpenAI auth method (1-2)", "1")
    auth_mode = "auth_token" if auth_choice == "2" else "api_key"
    env_name = _provider_prompt_name("openai", auth_mode)
    secret = _secret_prompt(f"{env_name}", os.environ.get(env_name, ""))
    if not secret:
        return "none", {}
    return auth_mode, {env_name: secret}


def _sync_auth_profiles(primary_provider: str, primary_auth_mode: str, openai_auth_mode: str) -> str:
    manager = AuthProfileManager()
    active_profile = ""

    if primary_provider in PROVIDER_PROMPTS and primary_auth_mode in {"api_key", "auth_token"}:
        env_name = _provider_prompt_name(primary_provider, primary_auth_mode)
        if os.environ.get(env_name):
            profile = manager.ensure_default_profile(
                primary_provider,
                primary_auth_mode,
                env_name,
                description=f"Active {primary_provider} runtime profile",
            )
            active_profile = profile.name

    if openai_auth_mode in {"api_key", "auth_token"}:
        env_name = _provider_prompt_name("openai", openai_auth_mode)
        if os.environ.get(env_name):
            manager.ensure_default_profile(
                "openai",
                openai_auth_mode,
                env_name,
                description="Optional OpenAI profile for adapters and tools",
            )

    return active_profile


def _run_self_test(provider: str, provider_secret: str = "") -> dict:
    results: dict[str, dict[str, object]] = {}

    try:
        from agi_runtime.tools.registry import ToolRegistry, discover_builtin_tools

        registry = ToolRegistry.get_instance()
        discover_builtin_tools()
        tools = registry.list_tools()
        results["tools"] = {"ok": len(tools) > 0, "count": len(tools)}
    except Exception as exc:
        results["tools"] = {"ok": False, "error": str(exc)}

    try:
        from agi_runtime.governance.srg import SRGGovernor

        governor = SRGGovernor()
        verdict = governor.evaluate_tool("bash_exec", {"command": "rm -rf /"}, "high")
        results["governance"] = {"ok": verdict.decision == "deny"}
    except Exception as exc:
        results["governance"] = {"ok": False, "error": str(exc)}

    try:
        from agi_runtime.memory.identity import IdentityEngine

        identity = IdentityEngine()
        results["identity"] = {"ok": identity.state.name is not None, "name": identity.state.name}
    except Exception as exc:
        results["identity"] = {"ok": False, "error": str(exc)}

    if provider == "anthropic" and provider_secret:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=provider_secret)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=32,
                messages=[{"role": "user", "content": "Reply with: HelloAGI ready"}],
            )
            text = response.content[0].text if response.content else ""
            results["llm"] = {"ok": True, "response": text[:60], "provider": "anthropic"}
        except Exception as exc:
            results["llm"] = {"ok": False, "error": str(exc)[:100], "provider": "anthropic"}
    elif provider == "google" and provider_secret:
        try:
            from google import genai

            client = genai.Client(api_key=provider_secret)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents="Reply with: HelloAGI ready",
            )
            text = getattr(response, "text", "") or "ok"
            results["llm"] = {"ok": True, "response": str(text)[:60], "provider": "google"}
        except Exception as exc:
            results["llm"] = {"ok": False, "error": str(exc)[:100], "provider": "google"}
    else:
        results["llm"] = {"ok": False, "error": "Template mode (no active runtime credential)", "provider": provider}

    try:
        from agi_runtime.skills.manager import SkillManager

        SkillManager()
        results["skills"] = {"ok": True}
    except Exception as exc:
        results["skills"] = {"ok": False, "error": str(exc)}

    return results


def run_wizard(path: str = "helloagi.onboard.json", options: WizardOptions | None = None):
    options = options or WizardOptions()
    _banner()
    from agi_runtime.onboarding.quotes import get_onboarding_quotes

    step_quotes = get_onboarding_quotes()
    total_steps = 7
    env = _detect_environment()

    _step(1, total_steps, "Environment and Import")
    print()
    _info(f"OS: {env['os']} | Python: {env['python']} | Shell: {env['shell']}")
    _info(f"Git: {'yes' if env.get('has_git') else 'no'} | Docker: {'yes' if env.get('has_docker') else 'no'}")
    for provider in ("anthropic", "google", "openai"):
        state = env["providers"].get(provider, {})
        if state.get("configured"):
            _ok(f"{provider.capitalize()} credential detected via {state.get('env_name')}")
    if env.get("has_telegram_token"):
        _ok("Telegram bot token already present")
    if env.get("has_discord_token"):
        _ok("Discord bot token already present")
    if env.get("has_service_auth_token"):
        _ok("HelloAGI service auth token already present")
    if env.get("has_rich"):
        _ok("Rich terminal UI available")
    else:
        _warn("Rich not installed. Run: pip install helloagi[rich]")
    if env.get("has_telegram_lib"):
        _ok("Telegram library available")
    else:
        _warn("Telegram library missing. Run: pip install 'helloagi[telegram]'")
    if env.get("has_discord_lib"):
        _ok("Discord library available")
    else:
        _warn("Discord library missing. Run: pip install 'helloagi[discord]'")
    if env.get("has_voice_lib"):
        _ok("Voice channel runtime available")
        for note in env.get("voice_runtime_notes", []):
            _info(str(note))
    else:
        _warn("Voice channel libraries missing. Run: pip install 'helloagi[voice]'")

    if options.import_source:
        migration_source, env = _apply_import_source(options.import_source)
    elif options.non_interactive:
        migration_source = ""
    else:
        migration_source, env = _maybe_import_existing_setup(env)
    print()

    _step(2, total_steps, "Agent Identity")
    print(f"    {DIM}{MAGENTA}\"{step_quotes[0]}\"{NC}")
    print(f"    {DIM}Give your agent a name and define who it serves.{NC}")
    print()
    settings = load_settings("helloagi.json")
    agent_name = (options.agent_name or "").strip() or settings.identity_name or "Lana"
    owner_name = (options.owner_name or "").strip()

    def _detect_host_tz() -> str:
        try:
            from datetime import datetime
            tz = datetime.now().astimezone().tzinfo
            key = getattr(tz, "key", None)
            if key:
                return key
        except Exception:
            pass
        return ""

    tz_default = (options.timezone or "").strip() or getattr(settings, "preferred_timezone", "") or _detect_host_tz()
    user_timezone = tz_default
    if not options.non_interactive:
        agent_name = _prompt("Agent name", agent_name)
        owner_name = _prompt("What should the agent call you", owner_name)
        user_timezone = _prompt("Your IANA timezone (e.g. Asia/Riyadh, Europe/London)", tz_default)
        if user_timezone and user_timezone != tz_default:
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(user_timezone)
            except Exception:
                _warn(f"'{user_timezone}' is not a valid IANA zone — keeping host-local.")
                user_timezone = tz_default
    print()

    _step(3, total_steps, "Runtime Profile")
    print(f"    {DIM}{MAGENTA}\"{step_quotes[1]}\"{NC}")
    print(f"    {DIM}Choose how HelloAGI should behave by default.{NC}")
    print()
    focus_map = {"1": "general", "2": "coding", "3": "research", "4": "creative"}
    pack_map = {"general": "safe-default", "coding": "coder", "research": "research", "creative": "creative"}
    focus = _normalize_focus(options.focus, "general")
    if not options.non_interactive:
        print(f"    {CYAN}1.{NC} General assistant")
        print(f"    {CYAN}2.{NC} Coding and development")
        print(f"    {CYAN}3.{NC} Research and analysis")
        print(f"    {CYAN}4.{NC} Creative work")
        focus_choice = _prompt("Focus (1-4)", "1")
        focus = focus_map.get(focus_choice, "general")

    print()
    runtime_mode = _normalize_runtime_mode(options.runtime_mode, "hybrid")
    if not options.non_interactive:
        print(f"    {CYAN}1.{NC} CLI only")
        print(f"    {CYAN}2.{NC} Hybrid local runtime {DIM}(CLI + service/channels){NC}")
        print(f"    {CYAN}3.{NC} Service-first")
        runtime_choice = _prompt("Runtime mode (1-3)", "2")
        runtime_mode = {"1": "cli", "2": "hybrid", "3": "service"}.get(runtime_choice, "hybrid")

    print()
    print(f"    {DIM}Model routing tier:{NC}")
    print(f"    {CYAN}speed{NC}    fast and cheap")
    print(f"    {CYAN}balanced{NC} default tradeoff")
    print(f"    {CYAN}quality{NC}  highest capability")
    default_tier = getattr(settings, "default_model_tier", "balanced")
    model_tier = _normalize_model_tier(options.model_tier, default_tier if default_tier in {"speed", "balanced", "quality"} else "balanced")
    if not options.non_interactive:
        model_tier = _prompt("Model tier", model_tier)
        if model_tier not in {"speed", "balanced", "quality"}:
            model_tier = "balanced"
            _warn("Unknown tier, using balanced.")
    print()

    _step(4, total_steps, "Primary Provider")
    print(f"    {DIM}HelloAGI runtime backbones today: template, Anthropic Claude, or Google Gemini.{NC}")
    print()
    provider_default = _provider_choice_default(env)
    primary_provider = _normalize_provider(options.provider, provider_default)
    if not options.non_interactive:
        print(f"    {CYAN}1.{NC} Template mode {DIM}(no active model credential yet){NC}")
        print(f"    {CYAN}2.{NC} Anthropic Claude")
        print(f"    {CYAN}3.{NC} Google Gemini")
        provider_choice = _prompt(
            "Active provider (1-3)",
            {"template": "1", "anthropic": "2", "google": "3"}[provider_default],
        )
        primary_provider = _provider_choice_label(provider_choice)
    primary_provider, primary_auth_mode, primary_env_updates = _configure_primary_provider(
        primary_provider,
        env,
        auth_mode=options.auth_mode,
        non_interactive=options.non_interactive,
    )
    provider_secret = ""
    if primary_provider in {"anthropic", "google"}:
        if primary_env_updates:
            env_name = next(iter(primary_env_updates))
            provider_secret = primary_env_updates[env_name]
            os.environ.setdefault(env_name, provider_secret)
        else:
            provider_secret = resolve_provider_credential(primary_provider, preferred_mode=primary_auth_mode).secret

    print()
    openai_auth_mode, openai_updates = _configure_optional_openai(env, non_interactive=options.non_interactive)
    if openai_updates:
        openai_env_name = next(iter(openai_updates))
        os.environ.setdefault(openai_env_name, openai_updates[openai_env_name])
    print()

    _step(5, total_steps, "Channels and Extensions")
    print(f"    {DIM}Enable channels now so first-run can already be chat-ready.{NC}")
    print()
    extension_manager = ExtensionManager()
    requested_extensions = {name.strip().lower() for name in options.enable_extensions if name.strip()}
    telegram_enabled = "telegram" in requested_extensions
    if not options.non_interactive:
        telegram_enabled = _yes_no_prompt("Enable Telegram bot", env.get("has_telegram_token"))
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if telegram_enabled and not telegram_token and not options.non_interactive:
        telegram_token = _secret_prompt("TELEGRAM_BOT_TOKEN")
    discord_enabled = "discord" in requested_extensions
    if not options.non_interactive:
        discord_enabled = _yes_no_prompt("Enable Discord bot", env.get("has_discord_token"))
    discord_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if discord_enabled and not discord_token and not options.non_interactive:
        discord_token = _secret_prompt("DISCORD_BOT_TOKEN")
    voice_enabled = "voice" in requested_extensions
    if not options.non_interactive:
        voice_enabled = _yes_no_prompt("Enable local voice channel", env.get("has_voice_lib"))

    google_ready = primary_provider == "google" and bool(provider_secret)
    embeddings_enabled = "embeddings" in requested_extensions
    if not options.non_interactive:
        embeddings_enabled = _yes_no_prompt("Enable semantic memory extension", google_ready)

    if telegram_enabled:
        extension_manager.enable("telegram")
    else:
        extension_manager.disable("telegram")
    if discord_enabled:
        extension_manager.enable("discord")
    else:
        extension_manager.disable("discord")
    if voice_enabled:
        extension_manager.enable("voice")
    else:
        extension_manager.disable("voice")
    if embeddings_enabled:
        extension_manager.enable("embeddings")
    else:
        extension_manager.disable("embeddings")
    enabled_extensions = extension_manager.enabled_names()
    for name in enabled_extensions:
        ext_status = extension_manager.status(name)
        if ext_status.missing_modules:
            _warn(f"{ext_status.title} is enabled but missing dependencies.")
            _info(f"Run: {extension_manager.install_command(name)}")
        if ext_status.missing_env:
            _warn(f"{ext_status.title} still needs env: {', '.join(ext_status.missing_env)}")
    print()

    _step(6, total_steps, "Service Auth and Runtime")
    print(f"    {DIM}HelloAGI secures its local API and dashboard with a shared auth token.{NC}")
    print()
    service_manager = ServiceManager()
    backend = service_manager._detect_backend()
    _info(f"Detected service backend: {backend}")
    service_token = (options.service_auth_token or "").strip() or os.environ.get("HELLOAGI_API_KEY", "")
    if service_token:
        os.environ["HELLOAGI_API_KEY"] = service_token
        _ok("Reusing existing HELLOAGI_API_KEY")
    elif runtime_mode in {"hybrid", "service"} or telegram_enabled or discord_enabled or voice_enabled:
        should_generate = options.non_interactive or _yes_no_prompt("Generate a HelloAGI service auth token now", True)
        if should_generate:
            service_token = os.urandom(24).hex()
            os.environ["HELLOAGI_API_KEY"] = service_token
            _ok("Generated local service auth token")
        else:
            _warn("No service auth token generated. Service mode will stay unavailable until you add HELLOAGI_API_KEY.")
    else:
        should_generate = False if options.non_interactive else _yes_no_prompt("Generate a local service auth token anyway", False)
        if should_generate:
            service_token = os.urandom(24).hex()
            os.environ["HELLOAGI_API_KEY"] = service_token
            _ok("Generated local service auth token")

    prepare_service = False
    service_install_state = None
    service_started_in_wizard = False
    if runtime_mode != "cli" or telegram_enabled or discord_enabled or voice_enabled:
        prepare_service = options.non_interactive or _yes_no_prompt("Prepare background service now", runtime_mode != "cli")
        if prepare_service:
            try:
                service_install_state = service_manager.install(
                    host="127.0.0.1",
                    port=8787,
                    config_path="helloagi.json",
                    policy_pack=pack_map.get(focus, "safe-default"),
                    telegram=telegram_enabled,
                    discord=discord_enabled,
                    enabled_extensions=enabled_extensions,
                    workdir=os.getcwd(),
                )
                if not service_token:
                    service_token = os.environ.get("HELLOAGI_API_KEY", "")
                _ok(f"Prepared HelloAGI service ({service_install_state.backend})")
                if service_install_state and service_install_state.installed:
                    if options.non_interactive:
                        _info("Background service is registered but not running. Run: helloagi service start")
                    elif _yes_no_prompt("Start the HelloAGI service now (channels go online after start)", True):
                        try:
                            service_manager.start()
                            service_started_in_wizard = True
                            _ok("Service start issued. Check: helloagi service status")
                        except Exception as exc:
                            _warn(f"Automatic start failed: {exc}. Run: helloagi service start")
                    else:
                        _info("Background service is installed but not started. Run: helloagi service start when ready.")
            except Exception as exc:
                _warn(f"Service preparation failed: {exc}")
    print()

    _step(7, total_steps, "Self-Test and Save")
    print(f"    {DIM}{MAGENTA}\"{step_quotes[2]}\"{NC}")
    print()
    test_results = _run_self_test(primary_provider, provider_secret)
    for name, result in test_results.items():
        if result.get("ok"):
            detail = ""
            if name == "tools":
                detail = f" ({result.get('count', 0)} tools)"
            elif name == "identity":
                detail = f" (agent: {result.get('name', '?')})"
            elif name == "llm":
                detail = f" ({result.get('provider', 'runtime')}: {str(result.get('response', ''))[:30]})"
            _ok(f"{name}{detail}")
        else:
            error = str(result.get("error", "unknown"))
            if name == "llm" and "Template mode" in error:
                _warn("llm: template mode")
            else:
                _fail(f"{name}: {error[:80]}")

    env_updates = {}
    env_updates.update(primary_env_updates)
    env_updates.update(openai_updates)
    if telegram_token:
        env_updates["TELEGRAM_BOT_TOKEN"] = telegram_token
    if discord_token:
        env_updates["DISCORD_BOT_TOKEN"] = discord_token
    if service_token:
        env_updates["HELLOAGI_API_KEY"] = service_token
    save_env_values(env_updates)
    load_local_env()
    active_profile = _sync_auth_profiles(primary_provider, primary_auth_mode, openai_auth_mode)

    settings = load_settings("helloagi.json")
    settings.identity_name = agent_name
    settings.name = "HelloAGI"
    settings.mission = f"Be the best {focus} assistant for {owner_name or 'the user'}"
    settings.llm_provider = primary_provider if primary_provider in {"anthropic", "google"} else "auto"
    settings.default_policy_pack = pack_map.get(focus, "safe-default")
    settings.default_model_tier = model_tier
    settings.runtime_mode = runtime_mode
    settings.preferred_timezone = user_timezone or ""
    save_settings(settings, "helloagi.json")

    Path("memory").mkdir(exist_ok=True)
    Path("memory/skills").mkdir(exist_ok=True)

    cfg = OnboardConfig(
        agent_name=agent_name,
        owner_name=owner_name,
        timezone=user_timezone or "UTC",
        default_model_tier=model_tier,
        focus=focus,
        providers=ProviderKeys(
            active_provider=primary_provider,
            active_auth_mode=primary_auth_mode,
            active_profile=active_profile,
            openai_api_key=bool(os.environ.get("OPENAI_API_KEY")),
            openai_auth_token=bool(os.environ.get("OPENAI_AUTH_TOKEN")),
            anthropic_api_key=bool(os.environ.get("ANTHROPIC_API_KEY")),
            anthropic_auth_token=bool(os.environ.get("ANTHROPIC_AUTH_TOKEN")),
            google_api_key=bool(os.environ.get("GOOGLE_API_KEY")),
            google_auth_token=bool(os.environ.get("GOOGLE_AUTH_TOKEN")),
        ),
        channels=ChannelKeys(
            telegram_bot_token=bool(telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")),
            telegram_enabled=telegram_enabled,
            discord_bot_token=bool(discord_token or os.environ.get("DISCORD_BOT_TOKEN")),
            discord_enabled=discord_enabled,
            voice_enabled=voice_enabled,
        ),
        service=ServiceSetup(
            runtime_mode=runtime_mode,
            auth_token=bool(service_token),
            background_service=bool(service_install_state and service_install_state.installed),
            backend=service_install_state.backend if service_install_state else backend,
            host="127.0.0.1",
            port=8787,
        ),
        extensions_enabled=enabled_extensions,
        migration_source=migration_source,
        env_detected=env,
        setup_complete=True,
    )
    _write_private_json(Path(path), _to_dict(cfg))

    print()
    passed = sum(1 for item in test_results.values() if item.get("ok"))
    total_checks = len(test_results)
    print(f"  {BOLD}{GREEN}Setup complete{NC} {DIM}({passed}/{total_checks} checks passed){NC}")
    print()
    print(f"    Agent:        {CYAN}{agent_name}{NC}")
    print(f"    Owner:        {CYAN}{owner_name or '(not set)'}{NC}")
    print(f"    Focus:        {CYAN}{focus}{NC} {DIM}(policy: {settings.default_policy_pack}){NC}")
    print(f"    Runtime:      {CYAN}{runtime_mode}{NC}")
    print(f"    Provider:     {CYAN}{primary_provider}{NC} {DIM}({primary_auth_mode}){NC}")
    if active_profile:
        print(f"    Auth profile: {CYAN}{active_profile}{NC}")
    print(f"    Model tier:   {CYAN}{model_tier}{NC}")
    print(f"    Service auth: {GREEN}configured{NC}" if service_token else f"    Service auth: {DIM}not configured{NC}")
    print(f"    Service:      {GREEN}prepared{NC}" if cfg.service.background_service else f"    Service:      {DIM}not prepared{NC}")
    print(f"    Extensions:   {CYAN}{', '.join(enabled_extensions) if enabled_extensions else 'none'}{NC}")
    if migration_source:
        print(f"    Imported:     {CYAN}{migration_source}{NC}")
    if cfg.service.background_service and service_install_state and service_install_state.installed:
        if not service_started_in_wizard:
            try:
                st = ServiceManager().status()
                if not st.get("running"):
                    print(
                        f"  {YELLOW}Note:{NC} Background service is installed but {BOLD}not running{NC} yet. "
                        f"Run: {BOLD}helloagi service start{NC}"
                    )
            except Exception:
                print(f"  {YELLOW}Note:{NC} Run {BOLD}helloagi service start{NC} when you want channels online.")
    print()
    print(f"  {BOLD}Next commands{NC}")
    print(f"    {CYAN}$ {NC}{BOLD}helloagi run{NC}")
    print(f"    {CYAN}$ {NC}{BOLD}helloagi health{NC}")
    if cfg.service.background_service:
        if not service_started_in_wizard:
            print(f"    {CYAN}$ {NC}{BOLD}helloagi service start{NC}")
        print(f"    {CYAN}$ {NC}{BOLD}helloagi service status{NC}")
    elif runtime_mode != "cli" or telegram_enabled or discord_enabled or voice_enabled:
        print(f"    {CYAN}$ {NC}{BOLD}helloagi service install --extension {' --extension '.join(enabled_extensions)}{NC}" if enabled_extensions else f"    {CYAN}$ {NC}{BOLD}helloagi service install{NC}")
        print(f"    {CYAN}$ {NC}{BOLD}helloagi service start{NC}")
    if telegram_enabled:
        print(f"    {DIM}Dev (foreground):{NC} {CYAN}$ {NC}{BOLD}helloagi serve --telegram{NC}")
    if discord_enabled:
        print(f"    {DIM}Dev (foreground):{NC} {CYAN}$ {NC}{BOLD}helloagi serve --discord{NC}")
    if voice_enabled:
        print(f"    {DIM}Dev (foreground):{NC} {CYAN}$ {NC}{BOLD}helloagi serve --voice{NC}")
    print(f"    {CYAN}$ {NC}{BOLD}helloagi onboard-status{NC}")
    print()
    if primary_provider == "template":
        print(f"  {YELLOW}Tip:{NC} add Anthropic or Google credentials later in `.env` and rerun `helloagi onboard`.")
        print()


def status(path: str = "helloagi.onboard.json"):
    onboard_path = Path(path)
    if not onboard_path.exists():
        print(f"{RED}Onboarding: not complete{NC}")
        print(f"  Run: {BOLD}helloagi onboard{NC}")
        return

    load_local_env()
    data = json.loads(onboard_path.read_text(encoding="utf-8"))
    providers = data.get("providers", {})
    channels = data.get("channels", {})
    service = data.get("service", {})
    env_snapshot = provider_env_snapshot()
    extensions_enabled = set(data.get("extensions_enabled", []))
    print(f"{GREEN}Onboarding: complete{NC}")
    print(f"  Agent:        {data.get('agent_name')}")
    print(f"  Owner:        {data.get('owner_name') or '(not set)'}")
    print(f"  Focus:        {data.get('focus', 'general')}")
    print(f"  Runtime:      {service.get('runtime_mode', 'hybrid')}")
    print(f"  Provider:     {providers.get('active_provider', 'template')} ({providers.get('active_auth_mode', 'none')})")
    if providers.get("active_profile"):
        print(f"  Auth profile: {providers.get('active_profile')}")
    ready_now = ", ".join(name for name, state in env_snapshot.items() if state.get("configured")) or "none"
    print(f"  Env ready:    {ready_now}")
    print(f"  Model tier:   {data.get('default_model_tier', 'balanced')}")
    print(f"  Migration:    {data.get('migration_source') or 'none'}")
    print("  Provider creds:")
    for label, api_key_field, token_field in (
        ("Anthropic", "anthropic_api_key", "anthropic_auth_token"),
        ("Google", "google_api_key", "google_auth_token"),
        ("OpenAI", "openai_api_key", "openai_auth_token"),
    ):
        provider_name = label.lower()
        env_state = env_snapshot.get(provider_name, {})
        api_state = f"{GREEN}set{NC}" if providers.get(api_key_field) or env_state.get("api_key") else f"{DIM}unset{NC}"
        token_state = f"{GREEN}set{NC}" if providers.get(token_field) or env_state.get("auth_token") else f"{DIM}unset{NC}"
        print(f"    {label}: api_key={api_state}, auth_token={token_state}")
    print("  Channels:")
    telegram = channels.get("telegram_enabled", False) or "telegram" in extensions_enabled or bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
    discord = channels.get("discord_enabled", False) or "discord" in extensions_enabled or bool(os.environ.get("DISCORD_BOT_TOKEN"))
    voice = channels.get("voice_enabled", False) or "voice" in extensions_enabled
    print(f"    Telegram: {'enabled' if telegram else 'disabled'}")
    print(f"    Discord:  {'enabled' if discord else 'disabled'}")
    print(f"    Voice:    {'enabled' if voice else 'disabled'}")
    print("  Service:")
    token_state = f"{GREEN}configured{NC}" if service.get("auth_token") or bool(os.environ.get("HELLOAGI_API_KEY")) else f"{DIM}not configured{NC}"
    prepared_state = f"{GREEN}prepared{NC}" if service.get("background_service") else f"{DIM}not prepared{NC}"
    print(f"    Auth token: {token_state}")
    print(f"    Background: {prepared_state}")
    print(f"    Backend:    {service.get('backend', 'process')}")
    extensions = sorted(extensions_enabled)
    print(f"  Extensions:   {', '.join(extensions) if extensions else 'none'}")


def is_onboarded(path: str = "helloagi.onboard.json") -> bool:
    onboard_path = Path(path)
    if not onboard_path.exists():
        return False
    try:
        data = json.loads(onboard_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(data.get("setup_complete"))
