from dataclasses import dataclass, asdict
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


def load_settings(path: str = "helloagi.json") -> RuntimeSettings:
    p = Path(path)
    if not p.exists():
        s = RuntimeSettings()
        p.write_text(json.dumps(asdict(s), indent=2))
        return s
    return RuntimeSettings(**json.loads(p.read_text()))


def save_settings(settings: RuntimeSettings, path: str = "helloagi.json"):
    Path(path).write_text(json.dumps(asdict(settings), indent=2))
