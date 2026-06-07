from __future__ import annotations

from pathlib import Path

from agi_runtime.config.settings import RuntimeSettings, save_settings
from agi_runtime.diagnostics.health import _build_service_recovery, format_health_report, run_health
from agi_runtime.service.manager import ServiceConfig, ServiceManager


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


def test_health_safe_mode_declares_diagnostics_only_runtime_policy(tmp_path, monkeypatch):
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

    safe_mode = report["safe_mode"]
    assert safe_mode["active"] is True
    assert safe_mode["enforced"] is True
    assert "health" in safe_mode["allowed_commands"]
    assert "doctor" in safe_mode["allowed_commands"]
    assert "auto" in safe_mode["blocked_runtime_actions"]
    assert "serve" not in safe_mode["blocked_runtime_actions"]
    assert "diagnostics-only" in safe_mode["recommendation"]

    rendered = format_health_report(report)
    assert "safe_mode_allowed_commands: health, doctor" in rendered
    assert "safe_mode_blocked_actions: auto" in rendered


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


def test_health_reports_service_and_channel_recovery_probes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "GOOGLE_API_KEY",
        "GOOGLE_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "OPENAI_AUTH_TOKEN",
        "TELEGRAM_BOT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HELLOAGI_OPENAI_OAUTH_DISABLE", "1")
    save_settings(RuntimeSettings(), "helloagi.json")
    Path("memory").mkdir()
    Path("memory/extensions_state.json").write_text('{"enabled": ["telegram"]}', encoding="utf-8")
    service_manifest = tmp_path / "missing.service"
    ServiceManager(state_path="memory/service_state.json", native_control=False).save(
        ServiceConfig(
            installed=True,
            native_registered=True,
            manifest_path=str(service_manifest),
            workdir=str(tmp_path),
            backend="systemd-user",
            telegram=True,
            enabled_extensions=["telegram"],
        )
    )

    report = run_health(config_path="helloagi.json", onboard_path="helloagi.onboard.json")

    assert report["service_recovery"]["ok"] is False
    assert "manifest_missing" in report["service_recovery"]["issues"]
    assert any("service reinstall" in item for item in report["service_recovery"]["recommendations"])
    telegram = report["channel_health"]["telegram"]
    assert telegram["enabled"] is True
    assert telegram["available"] is False
    assert "TELEGRAM_BOT_TOKEN" in telegram["missing_env"]
    assert "Run:" in telegram["recovery_hint"] or "Set env:" in telegram["recovery_hint"]

    rendered = format_health_report(report)
    assert "service_recovery:" in rendered
    assert "manifest_missing" in rendered
    assert "channel_status:" in rendered
    assert "telegram: enabled / not available" in rendered
    assert "TELEGRAM_BOT_TOKEN" in rendered


def test_health_redacts_service_recovery_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HELLOAGI_OPENAI_OAUTH_DISABLE", "1")
    save_settings(RuntimeSettings(), "helloagi.json")
    Path("memory").mkdir()
    manifest = tmp_path / "helloagi.service"
    manifest.write_text("ExecStart=/some/other/python -m agi_runtime.cli serve", encoding="utf-8")
    ServiceManager(state_path="memory/service_state.json", native_control=False).save(
        ServiceConfig(
            installed=True,
            native_registered=True,
            manifest_path=str(manifest),
            workdir=str(tmp_path),
            backend="systemd-user",
        )
    )

    report = run_health(config_path="helloagi.json", onboard_path="helloagi.onboard.json")
    rendered = format_health_report(report)

    assert "interpreter_path_mismatch" in report["service_recovery"]["issues"]
    assert "<path>" in rendered
    assert str(tmp_path) not in rendered
    assert "/usr/bin" not in rendered


def test_service_recovery_redacts_paths_with_spaces():
    class FakeServiceManager:
        def doctor(self):
            return {
                "ok": False,
                "installed": True,
                "issues": ["interpreter_path_mismatch"],
                "recommendations": [
                    "Manifest does not reference the current interpreter (/home/alice/My Project/.venv/bin/python). Run `helloagi service reinstall`.",
                    "Windows interpreter mismatch (C:\\Users\\Alice Smith\\HelloAGI\\.venv\\Scripts\\python.exe). Run reinstall.",
                ],
                "notes": [
                    "Inspect `/home/alice/My Project/logs/service.log` only locally.",
                    'Quoted POSIX path "/home/alice/My Project/logs/service.log" must be redacted.',
                    "Quoted Windows path 'C:\\Users\\Alice Smith\\HelloAGI\\logs\\service.log' must be redacted.",
                ],
                "backend": "systemd-user",
            }

    recovery = _build_service_recovery(FakeServiceManager())
    rendered = format_health_report({"service_recovery": recovery})

    assert "<path>" in rendered
    assert "alice" not in rendered
    assert "My Project" not in rendered
    assert "Alice Smith" not in rendered
    assert "Smith\\HelloAGI" not in rendered
