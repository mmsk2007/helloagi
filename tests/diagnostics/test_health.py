from __future__ import annotations

from pathlib import Path

from agi_runtime.config.settings import RuntimeSettings, save_settings
from agi_runtime.diagnostics.health import format_health_report, run_health


def test_health_reports_organ_categories_and_safe_mode_without_provider_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "GOOGLE_API_KEY",
        "GOOGLE_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "OPENAI_AUTH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HELLOAGI_OPENAI_OAUTH_DISABLE", "1")
    save_settings(RuntimeSettings(), "helloagi.json")
    Path("memory").mkdir()
    Path("memory/events.jsonl").write_text("", encoding="utf-8")
    Path("memory/helloagi.db").write_text("", encoding="utf-8")

    report = run_health(config_path="helloagi.json", onboard_path="helloagi.onboard.json")

    organ_health = report["organ_health"]
    assert set(organ_health) >= {
        "brain",
        "senses",
        "effectors",
        "immune",
        "memory",
        "metabolism",
        "channels",
        "homeostasis",
    }
    assert organ_health["brain"]["status"] == "action_required"
    assert "Configure at least one usable LLM provider" in organ_health["brain"]["recommendation"]
    assert organ_health["immune"]["status"] == "ok"
    assert report["safe_mode"]["active"] is True
    assert "brain" in report["safe_mode"]["critical_organs"]


def test_health_marks_brain_ok_when_any_provider_is_llm_usable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "a" * 32)
    monkeypatch.setenv("HELLOAGI_OPENAI_OAUTH_DISABLE", "1")
    save_settings(RuntimeSettings(), "helloagi.json")
    Path("memory").mkdir()
    Path("memory/events.jsonl").write_text("", encoding="utf-8")
    Path("memory/helloagi.db").write_text("", encoding="utf-8")

    report = run_health(config_path="helloagi.json", onboard_path="helloagi.onboard.json")

    assert report["organ_health"]["brain"]["status"] == "ok"
    assert report["safe_mode"]["active"] is False


def test_health_reports_provider_configured_vs_usable_and_recovery_hints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in (
        "ANTHROPIC_AUTH_TOKEN",
        "GOOGLE_API_KEY",
        "GOOGLE_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "OPENAI_AUTH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("HELLOAGI_OPENAI_OAUTH_DISABLE", "1")
    save_settings(RuntimeSettings(), "helloagi.json")

    report = run_health(config_path="helloagi.json", onboard_path="helloagi.onboard.json")

    providers = report["provider_health"]
    assert providers["anthropic"]["configured"] is True
    assert providers["anthropic"]["usable"] is False
    assert providers["anthropic"]["auth_mode"] == "api_key"
    assert "set a real ANTHROPIC_API_KEY" in providers["anthropic"]["recovery_hint"]
    assert providers["anthropic"]["secret_present"] is True
    assert "sk-ant-test" not in str(providers)

    rendered = format_health_report(report)
    assert "provider_status:" in rendered
    assert "anthropic: configured / not usable" in rendered
    assert "set a real ANTHROPIC_API_KEY" in rendered
    assert "sk-ant-test" not in rendered


def test_format_health_report_renders_organ_health_and_safe_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "GOOGLE_API_KEY",
        "GOOGLE_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "OPENAI_AUTH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HELLOAGI_OPENAI_OAUTH_DISABLE", "1")
    save_settings(RuntimeSettings(), "helloagi.json")

    report = run_health(config_path="helloagi.json", onboard_path="helloagi.onboard.json")
    rendered = format_health_report(report)

    assert "HelloAGI organism health:" in rendered
    assert "brain: action_required" in rendered
    assert "homeostasis: degraded" in rendered
    assert "safe_mode: active" in rendered
    assert "Configure at least one usable LLM provider" in rendered
