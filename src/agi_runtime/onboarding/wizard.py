"""HelloAGI Onboarding Wizard — professional interactive setup experience."""

from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import sys
import os
import shutil


# ── ANSI helpers ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
NC = "\033[0m"

# Disable colours when piped / non-interactive
if not sys.stdout.isatty():
    BOLD = DIM = CYAN = GREEN = YELLOW = RED = MAGENTA = NC = ""


def _banner():
    width = min(shutil.get_terminal_size().columns, 72)
    line = "─" * width
    print()
    print(f"{BOLD}{CYAN}  ╦ ╦╔═╗╦  ╦  ╔═╗╔═╗╔═╗╦{NC}")
    print(f"{BOLD}{CYAN}  ╠═╣║╣ ║  ║  ║ ║╠═╣║ ╦║{NC}")
    print(f"{BOLD}{CYAN}  ╩ ╩╚═╝╩═╝╩═╝╚═╝╩ ╩╚═╝╩{NC}")
    print()
    print(f"  {BOLD}The first open-source AGI runtime{NC}")
    print(f"  {DIM}Governed autonomy · Evolving identity · Local-first{NC}")
    print(f"  {DIM}{line}{NC}")
    print()


def _step(num: int, total: int, label: str):
    print(f"  {MAGENTA}[{num}/{total}]{NC} {BOLD}{label}{NC}")


def _prompt(label: str, default: str = "") -> str:
    hint = f" {DIM}({default}){NC}" if default else ""
    try:
        val = input(f"       {label}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val or default


def _secret_prompt(label: str) -> str:
    hint = f" {DIM}(press Enter to skip){NC}"
    try:
        val = input(f"       {label}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    return val


def _ok(msg: str):
    print(f"  {GREEN}✓{NC} {msg}")


def _warn(msg: str):
    print(f"  {YELLOW}!{NC} {msg}")


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class ProviderKeys:
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""


@dataclass
class OnboardConfig:
    agent_name: str = "HelloAGI"
    owner_name: str = ""
    timezone: str = "UTC"
    default_model_tier: str = "balanced"
    providers: ProviderKeys = field(default_factory=ProviderKeys)


def _to_dict(cfg: OnboardConfig) -> dict:
    return asdict(cfg)


# ── Wizard ────────────────────────────────────────────────────────────────────

def run_wizard(path: str = "helloagi.onboard.json"):
    _banner()

    total = 4
    # Step 1: Agent identity
    _step(1, total, "Agent Identity")
    print(f"       {DIM}Give your agent a name and tell it who you are.{NC}")
    agent_name = _prompt("Agent name", "HelloAGI")
    owner_name = _prompt("Your name (owner)")
    print()

    # Step 2: Environment
    _step(2, total, "Environment")
    print(f"       {DIM}Configure timezone and default model routing tier.{NC}")
    timezone = _prompt("Timezone", "UTC")
    print(f"       {DIM}Tiers: speed (fast, cheaper) | balanced | quality (slower, best){NC}")
    tier = _prompt("Default model tier", "balanced")
    if tier not in ("speed", "balanced", "quality"):
        _warn(f"Unknown tier '{tier}', falling back to 'balanced'.")
        tier = "balanced"
    print()

    # Step 3: API keys
    _step(3, total, "Provider API Keys")
    print(f"       {DIM}Keys are stored locally in {path}.{NC}")
    print(f"       {DIM}HelloAGI works without keys (local/template mode).{NC}")
    print(f"       {DIM}Add keys later via .env or re-run: helloagi onboard{NC}")
    print()
    anthropic = _secret_prompt("ANTHROPIC_API_KEY")
    openai = _secret_prompt("OPENAI_API_KEY")
    google = _secret_prompt("GOOGLE_API_KEY")
    print()

    # Step 4: Save & verify
    _step(4, total, "Saving Configuration")
    cfg = OnboardConfig(
        agent_name=agent_name,
        owner_name=owner_name,
        timezone=timezone,
        default_model_tier=tier,
        providers=ProviderKeys(
            openai_api_key=openai,
            anthropic_api_key=anthropic,
            google_api_key=google,
        ),
    )

    p = Path(path)
    p.write_text(json.dumps(_to_dict(cfg), indent=2))
    _ok(f"Config saved to {BOLD}{path}{NC}")

    # Summary
    print()
    print(f"  {BOLD}{'─' * 50}{NC}")
    print(f"  {BOLD}Onboarding Complete{NC}")
    print(f"  {BOLD}{'─' * 50}{NC}")
    print()
    print(f"  Agent name:    {CYAN}{agent_name}{NC}")
    print(f"  Owner:         {CYAN}{owner_name or '(not set)'}{NC}")
    print(f"  Timezone:      {CYAN}{timezone}{NC}")
    print(f"  Model tier:    {CYAN}{tier}{NC}")
    print(f"  Anthropic key: {GREEN}set{NC}" if anthropic else f"  Anthropic key: {DIM}not set{NC}")
    print(f"  OpenAI key:    {GREEN}set{NC}" if openai else f"  OpenAI key:    {DIM}not set{NC}")
    print(f"  Google key:    {GREEN}set{NC}" if google else f"  Google key:    {DIM}not set{NC}")
    print()

    # Next steps
    print(f"  {BOLD}Next steps:{NC}")
    print()
    print(f"  {CYAN}1.{NC} Initialize runtime config:")
    print(f"     {BOLD}helloagi init{NC}")
    print()
    print(f"  {CYAN}2.{NC} Verify everything works:")
    print(f"     {BOLD}helloagi doctor{NC}")
    print()
    print(f"  {CYAN}3.{NC} Start your first session:")
    print(f"     {BOLD}helloagi run --goal \"Build useful intelligence\"{NC}")
    print()
    print(f"  {CYAN}4.{NC} Or try autonomous mode:")
    print(f"     {BOLD}helloagi auto --goal \"ship v1\" --steps 5{NC}")
    print()

    if not anthropic:
        _warn("No Anthropic key set. Agent runs in template mode.")
        _warn(f"Set it later: {BOLD}export ANTHROPIC_API_KEY=sk-ant-...{NC}")
        print()


def status(path: str = "helloagi.onboard.json"):
    p = Path(path)
    if not p.exists():
        print(f"{RED}onboard: missing{NC} (run `helloagi onboard`)")
        return
    data = json.loads(p.read_text())
    providers = data.get("providers", {})

    print(f"{GREEN}onboard: ok{NC}")
    print(f"  agent_name:         {data.get('agent_name')}")
    print(f"  owner_name:         {data.get('owner_name') or '(not set)'}")
    print(f"  timezone:           {data.get('timezone')}")
    print(f"  default_model_tier: {data.get('default_model_tier')}")
    print(f"  provider_keys:")
    for k in ["openai_api_key", "anthropic_api_key", "google_api_key"]:
        v = providers.get(k, "")
        status_str = f"{GREEN}set{NC}" if v else f"{DIM}missing{NC}"
        print(f"    {k}: {status_str}")
