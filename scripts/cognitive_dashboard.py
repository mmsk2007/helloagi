"""Cognitive runtime dashboard.

Reads the journal + trace store + skill bank and prints a snapshot:

  - Routing mix: System 1 vs System 2 over the last N events
  - System 1 outcomes: success rate, recent failure reasons
  - System 2 outcomes: pass/fail/partial counts, average rounds
  - Skill graduations: how many crystallized in the window, names
  - Per-agent vote weights (so calibration drift is visible)

Usage:
    python -m scripts.cognitive_dashboard
    python -m scripts.cognitive_dashboard --window 200
    python -m scripts.cognitive_dashboard --journal memory/events.jsonl

Read-only — safe to run against a live install.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, List

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _read_journal(path: Path, *, limit: int) -> List[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: List[dict] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _section(title: str) -> None:
    print(f"\n[{title}]")


def _routing_mix(events: Iterable[dict]) -> None:
    counts = Counter()
    for e in events:
        if e.get("kind") != "routing.decided":
            continue
        sys_choice = (e.get("payload") or {}).get("system", "?")
        counts[sys_choice] += 1
    total = sum(counts.values())
    _section("routing")
    if total == 0:
        print("  (no routing events)")
        return
    for k in ("system1", "system2"):
        n = counts.get(k, 0)
        pct = 100.0 * n / total if total else 0.0
        print(f"  {k:<8} {n:>5}  ({pct:5.1f}%)")


def _system1_outcomes(events: Iterable[dict]) -> None:
    succ = 0
    fail = 0
    reasons = Counter()
    for e in events:
        if e.get("kind") != "system1.outcome":
            continue
        p = e.get("payload") or {}
        if p.get("success"):
            succ += 1
        else:
            fail += 1
            r = p.get("failure_reason") or "unknown"
            reasons[r] += 1
    _section("system 1 outcomes")
    total = succ + fail
    if total == 0:
        print("  (none)")
        return
    rate = 100.0 * succ / total
    print(f"  total={total}  pass={succ}  fail={fail}  pass_rate={rate:.1f}%")
    if reasons:
        print("  top failure reasons:")
        for r, n in reasons.most_common(5):
            print(f"    {r}: {n}")


def _system2_outcomes(events: Iterable[dict]) -> None:
    counts = Counter()
    fail_reasons = Counter()
    for e in events:
        if e.get("kind") != "system2.outcome":
            continue
        p = e.get("payload") or {}
        outcome = p.get("outcome") or ("pass" if p.get("success") else "fail")
        counts[outcome] += 1
        if not p.get("success"):
            fail_reasons[p.get("failure_reason") or "unknown"] += 1
    _section("system 2 outcomes")
    if not counts:
        print("  (none)")
        return
    for k in ("pass", "partial", "fail"):
        if k in counts:
            print(f"  {k:<7} {counts[k]}")
    if fail_reasons:
        print("  top failure reasons:")
        for r, n in fail_reasons.most_common(5):
            print(f"    {r}: {n}")


def _skill_graduations(events: Iterable[dict]) -> None:
    crystallized = []
    refreshed = []
    for e in events:
        if e.get("kind") != "skill.crystallized":
            continue
        p = e.get("payload") or {}
        if not p.get("crystallized"):
            continue
        bucket = refreshed if p.get("reason") == "refreshed" else crystallized
        bucket.append(p)
    _section("skill graduations")
    print(f"  crystallized: {len(crystallized)}")
    print(f"  refreshed   : {len(refreshed)}")
    for p in crystallized[-5:]:
        print(
            f"    + {p.get('skill_name', '?')}  "
            f"(fp={p.get('fingerprint', '?')}, "
            f"agreement={p.get('agreement', '?')})"
        )


def _trace_summary(store_path: Path) -> None:
    _section("council traces")
    if not store_path.exists():
        print("  (no trace store)")
        return
    try:
        from agi_runtime.cognition.trace import ThinkingTraceStore
    except Exception as exc:  # pragma: no cover
        print(f"  (failed to import trace store: {exc})")
        return
    store = ThinkingTraceStore(path=str(store_path))
    traces = store.find_recent(limit=200)
    if not traces:
        print("  (none)")
        return
    rounds = [len(t.rounds) for t in traces if t.rounds]
    avg_rounds = sum(rounds) / len(rounds) if rounds else 0.0
    outcomes = Counter((t.outcome or "pending") for t in traces)
    print(f"  total={len(traces)}  avg_rounds={avg_rounds:.2f}")
    for k in ("pass", "partial", "fail", "pending"):
        if k in outcomes:
            print(f"  {k:<7} {outcomes[k]}")


def _agent_weights(weights_path: Path) -> None:
    _section("agent vote weights")
    if not weights_path.exists():
        print("  (no weights file - council has not run yet)")
        return
    try:
        data = json.loads(weights_path.read_text(encoding="utf-8"))
    except Exception:
        print("  (unreadable)")
        return
    if not isinstance(data, dict) or not data:
        print("  (empty)")
        return
    for name, w in sorted(data.items()):
        bar = "#" * max(1, int(float(w) * 6))
        print(f"  {name:<14} {float(w):.2f}  {bar}")


def _skill_bank_summary(skills_dir: Path) -> None:
    _section("skill bank")
    if not skills_dir.exists():
        print("  (none)")
        return
    files = sorted(skills_dir.glob("*.skill.json"))
    if not files:
        print("  (no skill files)")
        return
    by_status = Counter()
    council_born = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        by_status[data.get("status", "?")] += 1
        if data.get("council_origin_trace_id"):
            council_born += 1
    print(f"  total={len(files)}  council_born={council_born}")
    for k, v in by_status.most_common():
        print(f"  {k:<10} {v}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--journal", default="memory/events.jsonl",
        help="Journal path (default: memory/events.jsonl)",
    )
    parser.add_argument(
        "--window", type=int, default=2000,
        help="Number of trailing journal lines to scan (default: 2000)",
    )
    parser.add_argument(
        "--traces", default="memory/cognition/traces",
        help="Trace store dir (default: memory/cognition/traces)",
    )
    parser.add_argument(
        "--weights", default="memory/cognition/agent_weights.json",
        help="Agent weights JSON (default: memory/cognition/agent_weights.json)",
    )
    parser.add_argument(
        "--skills", default="memory/skills",
        help="Skill bank dir (default: memory/skills)",
    )
    args = parser.parse_args()

    print("HelloAGI Cognitive Dashboard")
    print("============================")
    events = _read_journal(Path(args.journal), limit=args.window)
    print(f"window: last {len(events)} journal events from {args.journal}")
    _routing_mix(events)
    _system1_outcomes(events)
    _system2_outcomes(events)
    _skill_graduations(events)
    _trace_summary(Path(args.traces))
    _agent_weights(Path(args.weights))
    _skill_bank_summary(Path(args.skills))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
