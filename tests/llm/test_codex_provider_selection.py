import os
import importlib.util
from unittest.mock import patch

from agi_runtime.config.settings import RuntimeSettings
from agi_runtime.core.agent import HelloAGIAgent
from agi_runtime.config.providers import ProviderCredential, provider_credential_usable_for_llm_backbone


def test_openai_codex_oauth_token_is_not_treated_as_sdk_usable():
    credential = ProviderCredential(
        provider="openai",
        auth_mode="auth_token",
        env_name="OPENAI_AUTH_TOKEN",
        secret="tok_" + "x" * 40,
        source="openai_codex_oauth",
    )

    assert provider_credential_usable_for_llm_backbone("openai", credential) is False


def test_agent_selects_codex_cli_for_openai_pref_with_codex_oauth(monkeypatch):
    credential = ProviderCredential(
        provider="openai",
        auth_mode="auth_token",
        env_name="OPENAI_AUTH_TOKEN",
        secret="tok_" + "x" * 40,
        source="openai_codex_oauth",
    )

    with patch.dict(os.environ, {"HELLOAGI_LLM_PROVIDER": "openai"}, clear=False):
        with patch("agi_runtime.core.agent.resolve_provider_credential") as resolve:
            def _resolve(provider):
                if provider == "openai":
                    return credential
                return ProviderCredential(provider=provider)

            resolve.side_effect = _resolve
            with patch.object(importlib.util, "find_spec", return_value=object()):
                with patch("agi_runtime.core.agent.shutil.which", return_value="/usr/bin/codex"):
                    agent = HelloAGIAgent(settings=RuntimeSettings())

    assert agent._llm_provider == "codex"
    assert agent._openai_client is None


def test_agent_prefers_openai_sdk_when_api_key_is_available(monkeypatch):
    credential = ProviderCredential(
        provider="openai",
        auth_mode="api_key",
        env_name="OPENAI_API_KEY",
        secret="sk-" + "a" * 40,
        source="env",
    )

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    with patch.dict(os.environ, {"HELLOAGI_LLM_PROVIDER": "openai"}, clear=False):
        with patch("agi_runtime.core.agent.resolve_provider_credential") as resolve:
            def _resolve(provider):
                if provider == "openai":
                    return credential
                return ProviderCredential(provider=provider)

            resolve.side_effect = _resolve
            with patch.object(importlib.util, "find_spec", return_value=object()):
                with patch.dict("sys.modules", {"openai": type("M", (), {"AsyncOpenAI": FakeAsyncOpenAI})}):
                    agent = HelloAGIAgent(settings=RuntimeSettings())

    assert agent._llm_provider == "openai"
    assert agent._openai_client is not None
