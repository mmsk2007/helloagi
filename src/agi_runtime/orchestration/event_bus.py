from dataclasses import dataclass, asdict
from typing import Callable, Dict, List
import time


@dataclass
class RuntimeEvent:
    ts: float
    kind: str
    payload: dict


Handler = Callable[[RuntimeEvent], None]


class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[Handler]] = {}

    def on(self, kind: str, handler: Handler):
        self._handlers.setdefault(kind, []).append(handler)

    def emit(self, kind: str, payload: dict):
        ev = RuntimeEvent(ts=time.time(), kind=kind, payload=payload)
        for h in self._handlers.get(kind, []):
            h(ev)
        for h in self._handlers.get("*", []):
            h(ev)
        return asdict(ev)
