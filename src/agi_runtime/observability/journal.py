from dataclasses import dataclass, asdict
from pathlib import Path
import json
import time


@dataclass
class Event:
    ts: float
    kind: str
    payload: dict


class Journal:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, payload: dict):
        ev = Event(ts=time.time(), kind=kind, payload=payload)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")
