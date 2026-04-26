"""Per-session browser state isolation (in-process MVP)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class BrowserSessionState:
    url: str = ""
    text_snapshot: str = ""
    meta: Dict[str, str] = field(default_factory=dict)


class BrowserSandbox:
    """Keeps navigation state keyed by principal/session id."""

    def __init__(self) -> None:
        self._sessions: Dict[str, BrowserSessionState] = {}

    def get(self, session_id: str) -> BrowserSessionState:
        sid = session_id or "default"
        if sid not in self._sessions:
            self._sessions[sid] = BrowserSessionState()
        return self._sessions[sid]

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id or "default", None)


_GLOBAL_SANDBOX = BrowserSandbox()


def get_sandbox() -> BrowserSandbox:
    return _GLOBAL_SANDBOX
