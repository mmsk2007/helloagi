"""Typed in-memory event spine for HelloAGI organ-system telemetry.

The event spine is intentionally lightweight and persistence-agnostic: callers
can append/read JSON-safe organ events without changing runtime behavior when no
consumer is attached. It gives the BioAgent organism architecture a shared
circulatory channel for observations, decisions, actions, and health signals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4


_ORGANS = {
    "brain",
    "cortex",
    "nervous",
    "senses",
    "effectors",
    "immune",
    "memory",
    "metabolism",
    "circulatory",
    "homeostasis",
    "growth",
}


@dataclass(frozen=True)
class OrganEvent:
    """A typed JSON-safe signal passed between organism organs."""

    event_id: str
    trace_id: str
    organ: str
    kind: str
    timestamp: str
    payload: dict[str, Any]
    provenance: str
    confidence: float
    verified: bool

    @classmethod
    def create(
        cls,
        *,
        trace_id: str,
        organ: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        provenance: str,
        confidence: float,
        verified: bool,
    ) -> "OrganEvent":
        if not trace_id:
            raise ValueError("trace_id is required")
        if organ not in _ORGANS:
            raise ValueError(f"unknown organ: {organ}")
        if not kind:
            raise ValueError("kind is required")
        if not provenance:
            raise ValueError("provenance is required")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        event_payload = dict(payload or {})
        try:
            json.dumps(event_payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be JSON-safe") from exc
        return cls(
            event_id=f"evt_{uuid4().hex[:12]}",
            trace_id=trace_id,
            organ=organ,
            kind=kind,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            payload=event_payload,
            provenance=provenance,
            confidence=confidence,
            verified=verified,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "organ": self.organ,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
            "provenance": self.provenance,
            "confidence": self.confidence,
            "verified": self.verified,
        }


class EventSpine:
    """In-memory append/read helper for organism events."""

    def __init__(self, events: Iterable[OrganEvent] | None = None) -> None:
        self._events = list(events or [])

    def append(
        self,
        *,
        trace_id: str,
        organ: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        provenance: str,
        confidence: float,
        verified: bool,
    ) -> OrganEvent:
        event = OrganEvent.create(
            trace_id=trace_id,
            organ=organ,
            kind=kind,
            payload=payload,
            provenance=provenance,
            confidence=confidence,
            verified=verified,
        )
        self._events.append(event)
        return event

    def read(self, *, trace_id: str | None = None) -> list[OrganEvent]:
        if trace_id is None:
            return list(self._events)
        return [event for event in self._events if event.trace_id == trace_id]

    def read_dicts(self, *, trace_id: str | None = None) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.read(trace_id=trace_id)]

    def record_agent_turn_start(self, *, trace_id: str, input_present: bool) -> OrganEvent:
        return self.append(
            trace_id=trace_id,
            organ="nervous",
            kind="agent_turn_start",
            payload={"input_present": input_present},
            provenance="agent:think",
            confidence=1.0,
            verified=True,
        )

    def record_agent_turn_end(self, *, trace_id: str, success: bool) -> OrganEvent:
        return self.append(
            trace_id=trace_id,
            organ="nervous",
            kind="agent_turn_end",
            payload={"success": success},
            provenance="agent:think",
            confidence=1.0,
            verified=True,
        )

    def record_context_plan(self, workspace: Any, *, provenance: str) -> OrganEvent:
        summary = workspace.summarize()
        items = summary["items"]
        observed_count = sum(1 for item in items if item["observed"])
        verified_count = sum(1 for item in items if item["verified"])
        generated_count = len(items) - observed_count
        return self.append(
            trace_id=workspace.trace_id,
            organ="brain",
            kind="context_plan_created",
            payload={
                "items_count": len(items),
                "observed_items": observed_count,
                "generated_items": generated_count,
                "verified_items": verified_count,
            },
            provenance=provenance,
            confidence=1.0,
            verified=verified_count == len(items),
        )
