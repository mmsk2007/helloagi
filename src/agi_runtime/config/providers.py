from __future__ import annotations

from dataclasses import dataclass
import os

from agi_runtime.auth.profiles import AuthProfileManager
from agi_runtime.config.env import resolve_env_value


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

RUNTIME_PROVIDERS = ("anthropic", "google", "openai")

# Values that look like real keys but are docs/tests — ignored for automatic LLM selection.
_ANTHROPIC_API_KEY_DENYLIST = frozenset(
    {
        "sk-ant-test",
        "sk-ant-api03-test",
    }
)
_PLACEHOLDER_FRAGMENTS = ("...", "your-api-key", "changeme", "replace-me", "xxx", "placeholder")


def provider_credential_usable_for_llm_backbone(provider: str, credential: ProviderCredential) -> bool:
    """True if this credential is non-empty and not an obvious doc/test placeholder.

    Used for ``HELLOAGI_LLM_PROVIDER=auto`` so a leftover example Anthropic key
    does not block Gemini (or vice versa) when another provider has a real key.
    Explicit ``anthropic`` / ``google`` preferences still use ``.configured`` only.
    """
    if not credential.configured:
        return False
    secret = credential.secret.strip()
    if not secret:
        return False
    low = secret.lower()
    for frag in _PLACEHOLDER_FRAGMENTS:
        if frag in low:
            return False

    if provider == "anthropic":
        if secret in _ANTHROPIC_API_KEY_DENYLIST or low in _ANTHROPIC_API_KEY_DENYLIST:
            return False
        if credential.auth_mode == "api_key":
            if not secret.startswith("sk-ant-"):
                return len(secret) >= 32
            return len(secret) >= 24
        return len(secret) >= 20

    if provider == "google":
        if credential.auth_mode == "api_key":
            return len(secret) >= 30
        return len(secret) >= 20

    if provider == "openai":
        if credential.auth_mode == "api_key":
            return len(secret) >= 20
        return len(secret) >= 20

    return len(secret) >= 16


@dataclass(frozen=True)
class ProviderCredential:
    provider: str
    auth_mode: str = "none"
    env_name: str | None = None
    secret: str = ""
    source: str = "none"
    profile_name: str | None = None

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


def resolve_provider_credential(
    provider: str,
    preferred_mode: str | None = None,
    *,
    env_path: str = ".env",
    auth_profiles_path: str = "memory/auth_profiles.json",
) -> ProviderCredential:
    provider_env = PROVIDER_SECRET_ENV.get(provider, {})
    mode_order = [preferred_mode] if preferred_mode in provider_env else []
    for candidate in ("api_key", "auth_token"):
        if candidate not in mode_order:
            mode_order.append(candidate)

    # Highest precedence: canonical env names already present in the runtime.
    for mode in mode_order:
        for env_name in provider_env.get(mode, []):
            secret = os.environ.get(env_name, "").strip()
            if secret:
                return ProviderCredential(
                    provider=provider,
                    auth_mode=mode,
                    env_name=env_name,
                    secret=secret,
                    source="env",
                )

    # Next: enabled auth profiles, which may reference custom env keys.
    profile_resolution = AuthProfileManager(path=auth_profiles_path, env_path=env_path).resolve(provider)
    if profile_resolution.get("configured"):
        return ProviderCredential(
            provider=provider,
            auth_mode=str(profile_resolution.get("auth_mode", "none")),
            env_name=profile_resolution.get("env_name"),
            secret=str(profile_resolution.get("secret", "")),
            source=str(profile_resolution.get("source", "auth_profile")),
            profile_name=profile_resolution.get("name"),
        )

    # Lowest precedence: canonical .env values without an active auth profile.
    for mode in mode_order:
        for env_name in provider_env.get(mode, []):
            secret = resolve_env_value(env_name, env_path)
            if secret:
                return ProviderCredential(
                    provider=provider,
                    auth_mode=mode,
                    env_name=env_name,
                    secret=secret,
                    source="local_env",
                )
    return ProviderCredential(provider=provider)


def provider_env_snapshot(*, env_path: str = ".env", auth_profiles_path: str = "memory/auth_profiles.json") -> dict[str, dict[str, object]]:
    snapshot: dict[str, dict[str, object]] = {}
    for provider in PROVIDER_SECRET_ENV:
        credential = resolve_provider_credential(provider, env_path=env_path, auth_profiles_path=auth_profiles_path)
        provider_state = {
            "configured": credential.configured,
            "llm_usable": provider_credential_usable_for_llm_backbone(provider, credential),
            "auth_mode": credential.auth_mode,
            "env_name": credential.env_name,
            "source": credential.source,
            "profile_name": credential.profile_name,
        }
        for mode in ("api_key", "auth_token"):
            provider_state[mode] = any(resolve_env_value(name, env_path) for name in env_names_for_provider(provider, mode))
        snapshot[provider] = provider_state
    return snapshot
