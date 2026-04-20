"""Shared voice presence state for local voice UI surfaces."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import threading
import time
from typing import Any


@dataclass
class VoicePresenceSnapshot:
    state: str = "inactive"
    detail: str = ""
    wake_word: str = "lana"
    active: bool = False
    last_heard: str = ""
    last_spoken: str = ""
    error: str = ""
    updated_at: float = 0.0
    version: int = 0


class VoicePresenceStore:
    """Thread-safe latest-state store for voice channel presence."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._state = VoicePresenceSnapshot(updated_at=time.time())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._state)

    def update(self, **fields: Any) -> dict[str, Any]:
        with self._cond:
            for key, value in fields.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
            self._state.updated_at = time.time()
            self._state.version += 1
            snap = asdict(self._state)
            self._cond.notify_all()
            return snap

    def wait_for_change(self, after_version: int, timeout: float = 15.0) -> dict[str, Any] | None:
        deadline = time.time() + timeout
        with self._cond:
            while self._state.version <= after_version:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._cond.wait(timeout=remaining)
            return asdict(self._state)


_VOICE_PRESENCE = VoicePresenceStore()


def voice_presence_store() -> VoicePresenceStore:
    return _VOICE_PRESENCE
