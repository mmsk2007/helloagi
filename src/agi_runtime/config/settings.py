from dataclasses import dataclass, asdict, fields
from pathlib import Path
import json


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
    # Which backbone powers agent.think(): auto | anthropic | google (env HELLOAGI_LLM_PROVIDER overrides)
    llm_provider: str = "auto"


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
