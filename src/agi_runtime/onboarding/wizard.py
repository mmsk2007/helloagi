"""HelloAGI Onboarding Wizard — beautiful interactive setup experience.

Runs automatically on first `helloagi run` if no config exists.
Detects environment, configures API keys, runs self-test, and
drops the user into a ready-to-go AGI session.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import sys
import os
import shutil
import platform
import time


# ── ANSI helpers ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
NC = "\033[0m"

# Disable colours when piped / non-interactive
if not sys.stdout.isatty():
    BOLD = DIM = CYAN = GREEN = YELLOW = RED = MAGENTA = BLUE = NC = ""


def _banner():
    from agi_runtime.onboarding.quotes import get_startup_quote
    quote = get_startup_quote()

    print()
    print(f"{BOLD}{CYAN}  ╦ ╦╔═╗╦  ╦  ╔═╗╔═╗╔═╗╦{NC}")
    print(f"{BOLD}{CYAN}  ╠═╣║╣ ║  ║  ║ ║╠═╣║ ╦║{NC}")
    print(f"{BOLD}{CYAN}  ╩ ╩╚═╝╩═╝╩═╝╚═╝╩ ╩╚═╝╩{NC}  {DIM}v0.5.0{NC}")
    print()
    print(f"  {BOLD}The first open-source AGI runtime{NC}")
    print(f"  {DIM}Governed autonomy  ·  Evolving identity  ·  Local-first{NC}")
    print()
    print(f"  {DIM}{MAGENTA}{quote}{NC}")
    print()


def _step(num: int, total: int, label: str):
    bar = f"{'█' * num}{'░' * (total - num)}"
    print(f"  {MAGENTA}[{bar}]{NC} {BOLD}Step {num}/{total}: {label}{NC}")


def _prompt(label: str, default: str = "") -> str:
    hint = f" {DIM}({default}){NC}" if default else ""
    try:
        val = input(f"    {CYAN}>{NC} {label}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val or default


def _secret_prompt(label: str) -> str:
    hint = f" {DIM}(press Enter to skip){NC}"
    try:
        val = input(f"    {CYAN}>{NC} {label}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    return val


def _ok(msg: str):
    print(f"    {GREEN}✓{NC} {msg}")


def _warn(msg: str):
    print(f"    {YELLOW}!{NC} {msg}")


def _fail(msg: str):
    print(f"    {RED}✗{NC} {msg}")


def _info(msg: str):
    print(f"    {BLUE}i{NC} {msg}")


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class ProviderKeys:
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""


@dataclass
class ChannelKeys:
    telegram_bot_token: str = ""


@dataclass
class OnboardConfig:
    agent_name: str = "HelloAGI"
    owner_name: str = ""
    timezone: str = "UTC"
    default_model_tier: str = "balanced"
    focus: str = "general"
    providers: ProviderKeys = field(default_factory=ProviderKeys)
    channels: ChannelKeys = field(default_factory=ChannelKeys)
    env_detected: dict = field(default_factory=dict)
    setup_complete: bool = False


def _to_dict(cfg: OnboardConfig) -> dict:
    return asdict(cfg)


def _write_private_json(path: Path, data: dict):
    """Persist onboarding data with best-effort private permissions."""
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


# ─��� Environment Detection ────────────────────────────────────────────────────

def _detect_environment() -> dict:
    """Auto-detect the user's environment for optimal configuration."""
    env = {
        "os": platform.system(),
        "os_version": platform.version(),
        "python": platform.python_version(),
        "shell": os.environ.get("SHELL", os.environ.get("COMSPEC", "unknown")),
    }

    # Check for common tools
    for tool in ["git", "docker", "node", "pip"]:
        env[f"has_{tool}"] = shutil.which(tool) is not None

    # Check for existing API keys in environment
    env["has_anthropic_key"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    env["has_openai_key"] = bool(os.environ.get("OPENAI_API_KEY"))
    env["has_google_key"] = bool(os.environ.get("GOOGLE_API_KEY"))
    env["has_telegram_token"] = bool(os.environ.get("TELEGRAM_BOT_TOKEN"))

    try:
        import telegram  # noqa: F401
        env["has_telegram_lib"] = True
    except ImportError:
        env["has_telegram_lib"] = False

    # Check for Rich library
    try:
        import rich
        env["has_rich"] = True
    except ImportError:
        env["has_rich"] = False

    return env


# ── Self-Test ─────────────────────────────────────────────────────────────────

def _run_self_test(anthropic_key: str = "") -> dict:
    """Run a quick self-test to verify everything works."""
    results = {}

    # Test 1: Tool registry
    try:
        from agi_runtime.tools.registry import ToolRegistry, discover_builtin_tools
        reg = ToolRegistry.get_instance()
        discover_builtin_tools()
        tools = reg.list_tools()
        results["tools"] = {"ok": len(tools) > 0, "count": len(tools)}
    except Exception as e:
        results["tools"] = {"ok": False, "error": str(e)}

    # Test 2: SRG governance
    try:
        from agi_runtime.governance.srg import SRGGovernor
        gov = SRGGovernor()
        r = gov.evaluate_tool("bash_exec", {"command": "rm -rf /"}, "high")
        results["governance"] = {"ok": r.decision == "deny"}
    except Exception as e:
        results["governance"] = {"ok": False, "error": str(e)}

    # Test 3: Identity engine
    try:
        from agi_runtime.memory.identity import IdentityEngine
        ie = IdentityEngine()
        results["identity"] = {"ok": ie.state.name is not None, "name": ie.state.name}
    except Exception as e:
        results["identity"] = {"ok": False, "error": str(e)}

    # Test 4: LLM connection
    if anthropic_key or os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key or None)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=50,
                messages=[{"role": "user", "content": "Say 'HelloAGI ready' in exactly 2 words."}],
            )
            text = resp.content[0].text if resp.content else ""
            results["llm"] = {"ok": True, "response": text[:50]}
        except Exception as e:
            results["llm"] = {"ok": False, "error": str(e)[:100]}
    else:
        results["llm"] = {"ok": False, "error": "No API key (template mode)"}

    # Test 5: Skill system
    try:
        from agi_runtime.skills.manager import SkillManager
        sm = SkillManager()
        results["skills"] = {"ok": True}
    except Exception as e:
        results["skills"] = {"ok": False, "error": str(e)}

    return results


# ── Wizard ────────────────────────────────────────────────────────────────────

def run_wizard(path: str = "helloagi.onboard.json"):
    _banner()

    from agi_runtime.onboarding.quotes import get_onboarding_quotes
    step_quotes = get_onboarding_quotes()

    total = 5

    # Step 1: Environment detection
    _step(1, total, "Detecting Environment")
    print()
    env = _detect_environment()
    _info(f"OS: {env['os']} | Python: {env['python']}")
    _info(f"Git: {'yes' if env.get('has_git') else 'no'} | Docker: {'yes' if env.get('has_docker') else 'no'}")

    if env.get("has_anthropic_key"):
        _ok("Anthropic API key found in environment")
    if env.get("has_openai_key"):
        _ok("OpenAI API key found in environment")
    if env.get("has_google_key"):
        _ok("Google API key found in environment")
    if env.get("has_telegram_token"):
        _ok("Telegram bot token found in environment")
    if env.get("has_rich"):
        _ok("Rich library available (beautiful terminal UI)")
    else:
        _warn("Rich not installed. Run: pip install helloagi[rich]")
    if env.get("has_telegram_lib"):
        _ok("Telegram library available")
    else:
        _warn("Telegram bot library not installed. Run: pip install 'helloagi[telegram]'")
    print()

    # Step 2: Agent Identity
    _step(2, total, "Agent Identity")
    print(f"    {DIM}{MAGENTA}\"{step_quotes[0]}\"{NC}")
    print(f"    {DIM}Give your agent a name and personality.{NC}")
    print(f"    {DIM}This is who it becomes — it evolves with every interaction.{NC}")
    print()
    agent_name = _prompt("Agent name", "Lana")
    owner_name = _prompt("What should I call you?", "")
    print()

    # Step 3: Focus & Model Tier
    _step(3, total, "Capabilities")
    print(f"    {DIM}{MAGENTA}\"{step_quotes[1]}\"{NC}")
    print(f"    {DIM}What should your agent be great at?{NC}")
    print()
    print(f"    {CYAN}1.{NC} General assistant (default)")
    print(f"    {CYAN}2.{NC} Coding & development")
    print(f"    {CYAN}3.{NC} Research & analysis")
    print(f"    {CYAN}4.{NC} Creative writing")
    print()
    focus_choice = _prompt("Choose (1-4)", "1")
    focus_map = {"1": "general", "2": "coding", "3": "research", "4": "creative"}
    pack_map = {"general": "safe-default", "coding": "coder", "research": "research", "creative": "creative"}
    focus = focus_map.get(focus_choice, "general")

    print()
    print(f"    {DIM}Model routing tier:{NC}")
    print(f"    {CYAN}speed{NC}    — Fast responses, lower cost (Haiku)")
    print(f"    {CYAN}balanced{NC} — Best mix of speed and quality (Sonnet)")
    print(f"    {CYAN}quality{NC}  — Maximum intelligence (Opus)")
    print()
    tier = _prompt("Model tier", "balanced")
    if tier not in ("speed", "balanced", "quality"):
        _warn(f"Unknown tier '{tier}', using 'balanced'.")
        tier = "balanced"
    print()

    # Step 4: API Keys
    _step(4, total, "API Keys")
    print(f"    {DIM}Keys are stored locally. HelloAGI works without keys (template mode).{NC}")
    print(f"    {DIM}For full AGI capabilities, at minimum set an Anthropic key.{NC}")
    print()

    anthropic_key = ""
    if env.get("has_anthropic_key"):
        _ok("Anthropic key already set in environment")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    else:
        anthropic_key = _secret_prompt("ANTHROPIC_API_KEY (sk-ant-...)")

    openai_key = ""
    if env.get("has_openai_key"):
        _ok("OpenAI key already set in environment")
    else:
        openai_key = _secret_prompt("OPENAI_API_KEY (optional)")

    google_key = ""
    if env.get("has_google_key"):
        _ok("Google key already set in environment")
    else:
        google_key = _secret_prompt("GOOGLE_API_KEY (optional, for embeddings)")

    telegram_token = ""
    print()
    print(f"    {DIM}Telegram is optional. Add a bot token now if you want chat-ready onboarding.{NC}")
    if env.get("has_telegram_token"):
        _ok("Telegram bot token already set in environment")
        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    else:
        telegram_token = _secret_prompt("TELEGRAM_BOT_TOKEN (optional, for helloagi serve --telegram)")
    print()

    # Step 5: Self-test & Save
    _step(5, total, "Self-Test & Configuration")
    print(f"    {DIM}{MAGENTA}\"{step_quotes[2]}\"{NC}")
    print()

    # Set key temporarily for self-test
    if anthropic_key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if telegram_token and not os.environ.get("TELEGRAM_BOT_TOKEN"):
        os.environ["TELEGRAM_BOT_TOKEN"] = telegram_token

    test_results = _run_self_test(anthropic_key)

    for name, result in test_results.items():
        if result["ok"]:
            detail = ""
            if name == "tools":
                detail = f" ({result.get('count', 0)} tools)"
            elif name == "identity":
                detail = f" (agent: {result.get('name', '?')})"
            elif name == "llm":
                detail = f" (response: {result.get('response', '')[:30]})"
            _ok(f"{name}{detail}")
        else:
            err = result.get("error", "unknown")
            if name == "llm" and "No API key" in err:
                _warn(f"{name}: template mode (no API key)")
            else:
                _fail(f"{name}: {err[:60]}")

    # Save configuration
    cfg = OnboardConfig(
        agent_name=agent_name,
        owner_name=owner_name,
        timezone="UTC",
        default_model_tier=tier,
        focus=focus,
        providers=ProviderKeys(
            openai_api_key=openai_key,
            anthropic_api_key=anthropic_key,
            google_api_key=google_key,
        ),
        channels=ChannelKeys(
            telegram_bot_token=telegram_token,
        ),
        env_detected=env,
        setup_complete=True,
    )

    p = Path(path)
    _write_private_json(p, _to_dict(cfg))

    # Also create helloagi.json if it doesn't exist
    config_path = Path("helloagi.json")
    if not config_path.exists():
        from agi_runtime.config.settings import RuntimeSettings, save_settings
        settings = RuntimeSettings()
        settings.mission = f"Be the best {focus} assistant for {owner_name or 'the user'}"
        save_settings(settings, str(config_path))

    # Create memory directory
    Path("memory").mkdir(exist_ok=True)
    Path("memory/skills").mkdir(exist_ok=True)

    print()

    # ── Beautiful Summary ─────────────────────────────────────────────────────

    passed = sum(1 for r in test_results.values() if r["ok"])
    total_tests = len(test_results)
    grade = "A+" if passed == total_tests else "A" if passed >= total_tests - 1 else "B" if passed >= total_tests - 2 else "C"

    width = min(shutil.get_terminal_size().columns, 60)
    line = "─" * width

    print(f"  {BOLD}{GREEN}{line}{NC}")
    print(f"  {BOLD}{GREEN}  Setup Complete!  Readiness: {grade} ({passed}/{total_tests} checks){NC}")
    print(f"  {BOLD}{GREEN}{line}{NC}")
    print()
    print(f"    Agent:      {CYAN}{BOLD}{agent_name}{NC}")
    print(f"    Owner:      {CYAN}{owner_name or '(not set)'}{NC}")
    print(f"    Focus:      {CYAN}{focus}{NC} (policy: {pack_map.get(focus, 'safe-default')})")
    print(f"    Model:      {CYAN}{tier}{NC}")
    print(f"    Tools:      {CYAN}{test_results.get('tools', {}).get('count', '?')}{NC} available")
    print(f"    LLM:        {GREEN}connected{NC}" if test_results.get("llm", {}).get("ok") else f"    LLM:        {YELLOW}template mode{NC}")
    print(f"    Telegram:   {GREEN}configured{NC}" if telegram_token or env.get("has_telegram_token") else f"    Telegram:   {DIM}not configured{NC}")
    print(f"    SRG:        {GREEN}active{NC} (deterministic governance)")
    print()

    # Quick-start commands
    print(f"  {BOLD}Get started:{NC}")
    print()
    print(f"    {CYAN}${NC} {BOLD}helloagi run{NC}")
    print(f"      {DIM}Interactive session with Rich TUI{NC}")
    print()
    print(f"    {CYAN}${NC} {BOLD}helloagi oneshot --message \"What can you do?\"{NC}")
    print(f"      {DIM}Single question, instant answer{NC}")
    print()
    print(f"    {CYAN}${NC} {BOLD}helloagi serve{NC}")
    print(f"      {DIM}Start HTTP API on localhost:8787{NC}")
    print()
    if telegram_token or env.get("has_telegram_token"):
        print(f"    {CYAN}${NC} {BOLD}helloagi serve --telegram{NC}")
        print(f"      {DIM}Start Telegram chat using your configured bot token{NC}")
        print()
    print(f"    {CYAN}${NC} {BOLD}helloagi dashboard{NC}")
    print(f"      {DIM}Live monitoring dashboard{NC}")
    print()

    if not anthropic_key and not env.get("has_anthropic_key"):
        print(f"  {YELLOW}Tip:{NC} For full AGI capabilities, set your API key:")
        print(f"    {BOLD}export ANTHROPIC_API_KEY=sk-ant-...{NC}")
        print()


def status(path: str = "helloagi.onboard.json"):
    p = Path(path)
    if not p.exists():
        print(f"{RED}Onboarding: not complete{NC}")
        print(f"  Run: {BOLD}helloagi onboard{NC}")
        return

    data = json.loads(p.read_text())
    providers = data.get("providers", {})
    channels = data.get("channels", {})

    print(f"{GREEN}Onboarding: complete{NC}")
    print(f"  Agent:      {data.get('agent_name')}")
    print(f"  Owner:      {data.get('owner_name') or '(not set)'}")
    print(f"  Focus:      {data.get('focus', 'general')}")
    print(f"  Model tier: {data.get('default_model_tier')}")
    print(f"  API keys:")
    for k in ["anthropic_api_key", "openai_api_key", "google_api_key"]:
        v = providers.get(k, "")
        label = k.replace("_api_key", "").capitalize()
        status_str = f"{GREEN}set{NC}" if v else f"{DIM}not set{NC}"
        print(f"    {label}: {status_str}")
    telegram_status = f"{GREEN}set{NC}" if channels.get("telegram_bot_token", "") else f"{DIM}not set{NC}"
    print(f"  Channels:")
    print(f"    Telegram: {telegram_status}")


def is_onboarded(path: str = "helloagi.onboard.json") -> bool:
    """Check if onboarding has been completed."""
    p = Path(path)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text())
        return data.get("setup_complete", False)
    except Exception:
        return False
