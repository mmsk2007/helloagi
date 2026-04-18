from __future__ import annotations

from dataclasses import dataclass
import os


PROVIDER_SECRET_ENV: dict[str, dict[str, list[str]]] = {
    "anthropic": {
        "api_key": ["ANTHROPIC_API_KEY"],
        "auth_token": ["ANTHROPIC_AUTH_TOKEN"],
    },
    "google": {
        "api_key": ["GOOGLE_API_KEY"],
        "auth_token": ["GOOGLE_AUTH_TOKEN"],
    },
    "openai": {
        "api_key": ["OPENAI_API_KEY"],
        "auth_token": ["OPENAI_AUTH_TOKEN"],
    },
}

RUNTIME_PROVIDERS = ("anthropic", "google")


@dataclass(frozen=True)
class ProviderCredential:
    provider: str
    auth_mode: str = "none"
    env_name: str | None = None
    secret: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.secret and self.env_name and self.auth_mode != "none")


def env_names_for_provider(provider: str, auth_mode: str | None = None) -> list[str]:
    provider_env = PROVIDER_SECRET_ENV.get(provider, {})
    if auth_mode:
        return list(provider_env.get(auth_mode, []))
    names: list[str] = []
    for mode in ("api_key", "auth_token"):
        names.extend(provider_env.get(mode, []))
    return names


def resolve_provider_credential(provider: str, preferred_mode: str | None = None) -> ProviderCredential:
    provider_env = PROVIDER_SECRET_ENV.get(provider, {})
    mode_order = [preferred_mode] if preferred_mode in provider_env else []
    for candidate in ("api_key", "auth_token"):
        if candidate not in mode_order:
            mode_order.append(candidate)

    for mode in mode_order:
        for env_name in provider_env.get(mode, []):
            secret = os.environ.get(env_name, "").strip()
            if secret:
                return ProviderCredential(
                    provider=provider,
                    auth_mode=mode,
                    env_name=env_name,
                    secret=secret,
                )
    return ProviderCredential(provider=provider)


def provider_env_snapshot() -> dict[str, dict[str, object]]:
    snapshot: dict[str, dict[str, object]] = {}
    for provider in PROVIDER_SECRET_ENV:
        credential = resolve_provider_credential(provider)
        provider_state = {
            "configured": credential.configured,
            "auth_mode": credential.auth_mode,
            "env_name": credential.env_name,
        }
        for mode in ("api_key", "auth_token"):
            provider_state[mode] = any(os.environ.get(name) for name in env_names_for_provider(provider, mode))
        snapshot[provider] = provider_state
    return snapshot
