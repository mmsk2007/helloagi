from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Any, Dict, Tuple
import json


_DEFAULT_OUTBOUND_EXTS: Tuple[str, ...] = (
    "txt", "md", "pdf", "csv", "json", "log",
    "png", "jpg", "jpeg", "gif", "webp",
    "mp3", "ogg", "wav", "m4a",
    "mp4", "mov", "webm",
    "zip", "tar", "gz",
)


def _default_reliability() -> Dict[str, Any]:
    return {
        "enabled": True,
        "loop_threshold": 3,
        "verify_completions": True,
        # 0 = disabled. When set, main think() loop stops with a user-visible message
        # after this many wall-clock seconds (Hermes/OpenClaw-style bounded runs).
        "soft_timeout_sec": 0,
    }


def _default_skill_bank() -> Dict[str, Any]:
    return {
        "enabled": True,
        "auto_extract": True,
        "decay_days": 30,
    }


def _default_context() -> Dict[str, Any]:
    return {
        "managed": True,
        "max_budget_tokens": 120000,
    }


def _default_browser() -> Dict[str, Any]:
    return {
        "enabled": True,
        "headless": True,
        "max_nav_per_min": 10,
    }


def _default_cognitive_runtime() -> Dict[str, Any]:
    return {
        # Master switch. False keeps behavior identical to pre-cognitive HelloAGI.
        "enabled": False,
        # observe | system1_only | dual
        "mode": "observe",
        # System 1 firing thresholds.
        "system1_relevance_threshold": 0.75,
        "system1_confidence_threshold": 0.70,
        # Above this risk score we always go System 2.
        "risk_escalation_threshold": 0.50,
        # How many recent fingerprints stay "seen" for novelty scoring.
        "novelty_lookback_events": 200,
        # Phase 3+: Agent Council configuration. Read but unused in observe.
        "council": {
            "agents": ["planner", "critic", "risk_auditor", "synthesizer"],
            "min_quorum": 3,
            "max_rounds": 2,
            "tie_breaker": "synthesizer",
        },
        # Phase 4+: when System 2 traces crystallize into Skills.
        "crystallization": {
            "min_council_successes": 3,
            "min_agent_agreement": 0.66,
        },
        # Mid-loop stall detector — catches "N silent tool-only turns in a
        # row" so the agent doesn't burn 40 turns floundering. ``enabled``
        # gates the warning injection itself; the detector still observes.
        "stall": {
            "enabled": True,
            "silent_turn_budget": 4,
            "warm_up_tool_calls": 5,
            "text_threshold": 40,
        },
    }


def _merge_section(default: Dict[str, Any], raw_val: Any) -> Dict[str, Any]:
    """Shallow-merge a feature section dict from JSON onto defaults."""
    out = dict(default)
    if isinstance(raw_val, dict):
        out.update(raw_val)
    return out


@dataclass
class RuntimeSettings:
    name: str = "HelloAGI"
    identity_name: str = "Lana"
    mission: str = "Help humans build safe, useful, high-impact systems"
    style: str = "direct, warm, strategic"
    domain_focus: str = "agents, products, automation"
    memory_path: str = "memory/identity_state.json"
    journal_path: str = "memory/events.jsonl"
    db_path: str = "memory/helloagi.db"
    # Which backbone powers agent.think(): auto | anthropic | google | openai
    # (env HELLOAGI_LLM_PROVIDER overrides)
    llm_provider: str = "auto"
    default_policy_pack: str = "safe-default"
    default_model_tier: str = "balanced"
    runtime_mode: str = "hybrid"
    preferred_timezone: str = ""
    # Outbound file/attachment policy. Empty workspace → resolve to cwd at use time.
    file_send_workspace: str = ""
    max_outbound_file_bytes: int = 20 * 1024 * 1024
    allowed_outbound_extensions: Tuple[str, ...] = field(
        default_factory=lambda: _DEFAULT_OUTBOUND_EXTS
    )
    # Feature sections (merged from helloagi.json — never silently dropped)
    reliability: Dict[str, Any] = field(default_factory=_default_reliability)
    skill_bank: Dict[str, Any] = field(default_factory=_default_skill_bank)
    context: Dict[str, Any] = field(default_factory=_default_context)
    browser: Dict[str, Any] = field(default_factory=_default_browser)
    cognitive_runtime: Dict[str, Any] = field(default_factory=_default_cognitive_runtime)


def load_settings(path: str = "helloagi.json") -> RuntimeSettings:
    p = Path(path)
    defaults = asdict(RuntimeSettings())
    if not p.exists():
        s = RuntimeSettings()
        p.write_text(json.dumps(asdict(s), indent=2))
        return s
    raw = json.loads(p.read_text())
    if not isinstance(raw, dict):
        raw = {}
    merged = {**defaults, **raw}
    allowed = {f.name for f in fields(RuntimeSettings)}
    filtered = {k: v for k, v in merged.items() if k in allowed}
    # Deep-merge dict feature sections so partial JSON does not wipe defaults
    filtered["reliability"] = _merge_section(
        dict(_default_reliability()), merged.get("reliability")
    )
    filtered["skill_bank"] = _merge_section(
        dict(_default_skill_bank()), merged.get("skill_bank")
    )
    filtered["context"] = _merge_section(
        dict(_default_context()), merged.get("context")
    )
    filtered["browser"] = _merge_section(
        dict(_default_browser()), merged.get("browser")
    )
    filtered["cognitive_runtime"] = _merge_section(
        dict(_default_cognitive_runtime()), merged.get("cognitive_runtime")
    )
    return RuntimeSettings(**filtered)


def save_settings(settings: RuntimeSettings, path: str = "helloagi.json"):
    Path(path).write_text(json.dumps(asdict(settings), indent=2))
