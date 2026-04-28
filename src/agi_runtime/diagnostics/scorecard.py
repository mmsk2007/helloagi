from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os
import sqlite3
import time

from agi_runtime.config.providers import provider_env_snapshot


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _load_json(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _check_db(db_path: str) -> Check:
    p = Path(db_path)
    if not p.exists():
        return Check("database", False, f"missing: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("SELECT 1 FROM schema_migrations LIMIT 1").fetchone()
            conn.execute("SELECT 1 FROM sessions LIMIT 1").fetchone()
            conn.execute("SELECT 1 FROM tasks LIMIT 1").fetchone()
        finally:
            conn.close()
        return Check("database", True, "sqlite + migrations present")
    except Exception as e:
        return Check("database", False, f"db check failed: {e}")


def _check_journal_health(journal_path: str) -> Check:
    p = Path(journal_path)
    if not p.exists():
        return Check("journal", False, f"missing: {journal_path}")

    raw_lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not raw_lines:
        return Check("journal", False, "journal exists but has no events")

    parsed_events: list[dict] = []
    skipped_lines = 0
    for line_no, raw in enumerate(raw_lines, start=1):
        try:
            event = json.loads(raw)
            if isinstance(event, dict):
                event.setdefault("_line", line_no)
                parsed_events.append(event)
            else:
                skipped_lines += 1
        except Exception:
            skipped_lines += 1

    if not parsed_events:
        return Check("journal", False, f"journal unreadable: {skipped_lines} invalid lines")

    latest_ts = None
    for event in reversed(parsed_events):
        ts = event.get("ts")
        if isinstance(ts, (int, float)):
            latest_ts = float(ts)
            break

    failure_events = sum(1 for event in parsed_events if event.get("kind") in {"deny", "failure"})
    detail_parts = [
        f"events={len(parsed_events)}",
        f"invalid_lines={skipped_lines}",
        f"failures={failure_events}",
    ]

    ok = skipped_lines == 0
    if latest_ts is not None:
        age_seconds = max(0.0, time.time() - latest_ts)
        detail_parts.append(f"last_event_age_s={int(age_seconds)}")
        if age_seconds > 24 * 60 * 60:
            ok = False
            detail_parts.append("stale")
    else:
        ok = False
        detail_parts.append("missing_ts")

    return Check("journal", ok, ", ".join(detail_parts))


def _check_provider_readiness(onboard: dict | None, *, env_path: str = ".env", auth_profiles_path: str = "memory/auth_profiles.json") -> Check:
    providers = onboard.get("providers", {}) if isinstance(onboard, dict) else {}
    env_snapshot = provider_env_snapshot(env_path=env_path, auth_profiles_path=auth_profiles_path)
    configured: list[str] = []
    for provider in ("openai", "anthropic", "google"):
        if not isinstance(providers, dict):
            continue
        if providers.get(f"{provider}_api_key") or providers.get(f"{provider}_auth_token"):
            configured.append(provider)
    env_ready = sorted(provider for provider, state in env_snapshot.items() if state.get("configured"))
    env_llm_usable = sorted(provider for provider, state in env_snapshot.items() if state.get("llm_usable"))
    available = sorted(set(configured) | set(env_ready))
    explicit_active_provider = providers.get("active_provider") if isinstance(providers, dict) else None
    active_provider = explicit_active_provider or "template"
    active_auth_mode = providers.get("active_auth_mode", "none") if isinstance(providers, dict) else "none"
    explicit_template = explicit_active_provider == "template"
    if "anthropic" in env_llm_usable:
        runtime_backbone = "anthropic-ready"
    elif "google" in env_llm_usable:
        runtime_backbone = "google-ready"
    elif "openai" in env_llm_usable:
        runtime_backbone = "openai-ready"
    elif active_provider == "google" and "google" in env_ready:
        runtime_backbone = "google-ready"
    elif active_provider == "openai" and "openai" in env_ready:
        runtime_backbone = "openai-ready"
    elif explicit_template:
        runtime_backbone = "template-only"
    elif active_provider in {"anthropic", "google", "openai"}:
        runtime_backbone = f"{active_provider}-missing"
    else:
        runtime_backbone = "anthropic-missing"

    detail_parts = [
        "available=" + (", ".join(available) if available else "none"),
        "configured=" + (", ".join(configured) if configured else "none"),
        "env=" + (", ".join(env_ready) if env_ready else "none"),
        "env_llm=" + (", ".join(env_llm_usable) if env_llm_usable else "none"),
        f"active={active_provider}",
        f"auth_mode={active_auth_mode}",
        "runtime_backbone=" + runtime_backbone,
    ]

    ok = bool(available) or explicit_template
    return Check("providers", ok, ", ".join(detail_parts))


def run_scorecard(config_path: str = "helloagi.json", onboard_path: str = "helloagi.onboard.json") -> dict:
    checks: list[Check] = []
    runtime_root = Path(config_path).resolve().parent
    env_path = str(runtime_root / ".env")
    auth_profiles_path = str(runtime_root / "memory" / "auth_profiles.json")

    cfg = _load_json(config_path)
    if cfg is None:
        checks.append(Check("config", False, f"missing/invalid: {config_path}"))
        db_path = "memory/helloagi.db"
        journal_path = "memory/events.jsonl"
    else:
        checks.append(Check("config", True, "ok"))
        db_path = cfg.get("db_path", "memory/helloagi.db")
        journal_path = cfg.get("journal_path", "memory/events.jsonl")

    onboard = _load_json(onboard_path)
    checks.append(Check("onboarding", onboard is not None, "ok" if onboard else f"missing: {onboard_path}"))

    checks.append(_check_db(db_path))
    checks.append(_check_journal_health(journal_path))
    checks.append(_check_provider_readiness(onboard, env_path=env_path, auth_profiles_path=auth_profiles_path))

    passed = sum(1 for c in checks if c.ok)
    total = len(checks)
    grade = round((passed / total) * 100) if total else 0

    return {
        "grade": grade,
        "passed": passed,
        "total": total,
        "checks": [asdict(c) for c in checks],
    }
