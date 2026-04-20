from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Tuple
import json


_DEFAULT_OUTBOUND_EXTS: Tuple[str, ...] = (
    "txt", "md", "pdf", "csv", "json", "log",
    "png", "jpg", "jpeg", "gif", "webp",
    "mp3", "ogg", "wav", "m4a",
    "mp4", "mov", "webm",
    "zip", "tar", "gz",
)


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
    # Which backbone powers agent.think(): auto | anthropic | google
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
    return RuntimeSettings(**filtered)


def save_settings(settings: RuntimeSettings, path: str = "helloagi.json"):
    Path(path).write_text(json.dumps(asdict(settings), indent=2))
