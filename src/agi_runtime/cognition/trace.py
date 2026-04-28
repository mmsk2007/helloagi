"""ThinkingTraceStore — queryable record of every System 2 council run.

Every council deliberation produces a ``CouncilTrace``: who said what each
round, who voted how, the synthesized final decision, the SRG verdict, and
(filled in later) whether the run actually worked. We persist these so:

  - **Debugging**: when the agent gets a hard task wrong, the human can
    see exactly which agent argued for what.
  - **Crystallization** (Phase 4): repeated successes on the same
    fingerprint distill into a System-1 skill so we don't re-debate
    next time.
  - **Replay** (Phase 5): re-run a trace_id against the current agent
    weights as a regression check.

Storage layout — one JSON file per trace plus a small index:

    memory/cognition/traces/
        _index.json              # fingerprint -> [trace_id, ...] + recency
        <trace_id>.json          # one trace per file

We avoid a single huge JSONL because ``update_outcome`` needs to mutate a
specific record (when the verifier reports back), and per-file makes that a
single atomic write rather than a stream rewrite. Volume is low — System 2
only fires on novel/risky tasks.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DebateRound:
    """One round of the council debate.

    ``agent_outputs`` maps agent name → that agent's argued position.
    ``critiques`` is a flat list of dissenting points raised this round.
    ``votes`` maps agent name → "yes"/"no"/"abstain" on the round's
    proposal (or any voting alphabet the council uses).
    """

    round_index: int = 0
    agent_outputs: Dict[str, str] = field(default_factory=dict)
    critiques: List[str] = field(default_factory=list)
    votes: Dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DebateRound":
        return cls(
            round_index=int(data.get("round_index", 0) or 0),
            agent_outputs=dict(data.get("agent_outputs") or {}),
            critiques=list(data.get("critiques") or []),
            votes=dict(data.get("votes") or {}),
            notes=str(data.get("notes") or ""),
        )


@dataclass
class CouncilTrace:
    """The full record of one System 2 deliberation."""

    trace_id: str = ""
    fingerprint: str = ""
    user_input: str = ""
    rounds: List[DebateRound] = field(default_factory=list)
    final_decision: str = ""
    reasoning_summary: str = ""
    srg_decision: Dict[str, Any] = field(default_factory=dict)
    # ``outcome`` is None until the verifier reports back. "pass"/"partial"/
    # "fail" are the recognized terminal states.
    outcome: Optional[str] = None
    agent_weights_at_run: Dict[str, float] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = "ct_" + uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rounds"] = [r.to_dict() if isinstance(r, DebateRound) else dict(r) for r in self.rounds]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CouncilTrace":
        rounds_raw = data.get("rounds") or []
        rounds = [
            r if isinstance(r, DebateRound) else DebateRound.from_dict(r)
            for r in rounds_raw
        ]
        return cls(
            trace_id=str(data.get("trace_id") or ""),
            fingerprint=str(data.get("fingerprint") or ""),
            user_input=str(data.get("user_input") or ""),
            rounds=rounds,
            final_decision=str(data.get("final_decision") or ""),
            reasoning_summary=str(data.get("reasoning_summary") or ""),
            srg_decision=dict(data.get("srg_decision") or {}),
            outcome=data.get("outcome"),
            agent_weights_at_run=dict(data.get("agent_weights_at_run") or {}),
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
        )


class ThinkingTraceStore:
    """Per-trace JSON files plus a lightweight index.

    All operations are best-effort: I/O errors get logged via the optional
    journal but never raised. The cognitive runtime should degrade
    gracefully if the trace store is unwritable, not crash the agent.
    """

    INDEX_FILENAME = "_index.json"

    def __init__(
        self,
        path: str = "memory/cognition/traces",
        *,
        journal: Any = None,
    ):
        self.dir = Path(path)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.journal = journal
        self._index_path = self.dir / self.INDEX_FILENAME
        self._index = self._load_index()

    # ── Public API ──────────────────────────────────────────────

    def write(self, trace: CouncilTrace) -> Path:
        """Persist a trace to disk and update the index."""
        if not trace.trace_id:
            trace.trace_id = "ct_" + uuid.uuid4().hex[:12]
        trace.updated_at = time.time()
        path = self._trace_path(trace.trace_id)
        self._atomic_write_json(path, trace.to_dict())
        self._record_in_index(trace)
        self._log("trace.written", {"trace_id": trace.trace_id, "fp": trace.fingerprint})
        return path

    def get(self, trace_id: str) -> Optional[CouncilTrace]:
        path = self._trace_path(trace_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return CouncilTrace.from_dict(data)
        except Exception:
            return None

    def find_by_fingerprint(self, fingerprint: str) -> List[CouncilTrace]:
        ids = list(self._index.get("by_fp", {}).get(fingerprint, []))
        out: List[CouncilTrace] = []
        for tid in ids:
            t = self.get(tid)
            if t is not None:
                out.append(t)
        # Newest first.
        out.sort(key=lambda t: t.created_at, reverse=True)
        return out

    def find_recent(self, limit: int = 50) -> List[CouncilTrace]:
        recents = sorted(
            self._index.get("recents", []),
            key=lambda r: r.get("created_at", 0.0),
            reverse=True,
        )[: max(0, int(limit))]
        out: List[CouncilTrace] = []
        for r in recents:
            t = self.get(r.get("trace_id", ""))
            if t is not None:
                out.append(t)
        return out

    def update_outcome(self, trace_id: str, outcome: str) -> bool:
        """Patch a trace with its verified outcome ("pass"/"partial"/"fail").

        Returns True iff the trace was found and updated.
        """
        trace = self.get(trace_id)
        if trace is None:
            return False
        trace.outcome = outcome
        trace.updated_at = time.time()
        self._atomic_write_json(self._trace_path(trace_id), trace.to_dict())
        # Index keeps recents up-to-date.
        for entry in self._index.get("recents", []):
            if entry.get("trace_id") == trace_id:
                entry["outcome"] = outcome
                entry["updated_at"] = trace.updated_at
                break
        self._save_index()
        self._log("trace.outcome", {"trace_id": trace_id, "outcome": outcome})
        return True

    # ── Internals ────────────────────────────────────────────────

    def _trace_path(self, trace_id: str) -> Path:
        # Defensive — trace_ids are generated, but we still strip to be safe.
        safe = "".join(ch for ch in trace_id if ch.isalnum() or ch in ("_", "-"))
        return self.dir / f"{safe}.json"

    def _load_index(self) -> dict:
        if not self._index_path.exists():
            return {"by_fp": {}, "recents": []}
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            data.setdefault("by_fp", {})
            data.setdefault("recents", [])
            return data
        except Exception:
            return {"by_fp": {}, "recents": []}

    def _save_index(self) -> None:
        try:
            self._atomic_write_json(self._index_path, self._index)
        except Exception:
            pass

    def _record_in_index(self, trace: CouncilTrace) -> None:
        by_fp = self._index.setdefault("by_fp", {})
        ids = by_fp.setdefault(trace.fingerprint, [])
        if trace.trace_id not in ids:
            ids.append(trace.trace_id)
        recents = self._index.setdefault("recents", [])
        # Replace any existing entry for this trace_id (e.g., re-write).
        recents = [r for r in recents if r.get("trace_id") != trace.trace_id]
        recents.append({
            "trace_id": trace.trace_id,
            "fingerprint": trace.fingerprint,
            "created_at": trace.created_at,
            "updated_at": trace.updated_at,
            "outcome": trace.outcome,
        })
        # Cap recents to a reasonable size — older entries still exist on disk.
        recents.sort(key=lambda r: r.get("created_at", 0.0), reverse=True)
        self._index["recents"] = recents[:500]
        self._save_index()

    def _atomic_write_json(self, path: Path, data: dict) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _log(self, kind: str, payload: dict) -> None:
        if self.journal is not None and hasattr(self.journal, "write"):
            try:
                self.journal.write(kind, payload)
            except Exception:
                pass


__all__ = ["DebateRound", "CouncilTrace", "ThinkingTraceStore"]
