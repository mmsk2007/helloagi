from dataclasses import dataclass, asdict, field
from pathlib import Path
import json


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
    d = asdict(cfg)
    return d


def run_wizard(path: str = "helloagi.onboard.json"):
    print("HelloAGI Onboarding Wizard")
    print("Press Enter to keep defaults.")

    agent_name = input("Agent name [HelloAGI]: ").strip() or "HelloAGI"
    owner_name = input("Your name: ").strip()
    timezone = input("Timezone [UTC]: ").strip() or "UTC"
    tier = input("Default model tier (speed|balanced|quality) [balanced]: ").strip() or "balanced"

    print("\nProvider API keys (optional now, can be set later):")
    openai = input("OPENAI_API_KEY: ").strip()
    anthropic = input("ANTHROPIC_API_KEY: ").strip()
    google = input("GOOGLE_API_KEY: ").strip()

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
    print(f"\nSaved onboarding config: {path}")
    print("Next: helloagi doctor && helloagi run --goal \"...\"")


def status(path: str = "helloagi.onboard.json"):
    p = Path(path)
    if not p.exists():
        print("onboard: missing (run `helloagi onboard`)")
        return
    data = json.loads(p.read_text())
    providers = data.get("providers", {})
    print("onboard: ok")
    print(f"agent_name={data.get('agent_name')}")
    print(f"owner_name={data.get('owner_name')}")
    print(f"timezone={data.get('timezone')}")
    print(f"default_model_tier={data.get('default_model_tier')}")
    print("provider_keys:")
    for k in ["openai_api_key", "anthropic_api_key", "google_api_key"]:
        v = providers.get(k, "")
        print(f"- {k}: {'set' if v else 'missing'}")
