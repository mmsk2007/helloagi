"""Replay a System 2 council trace.

Two modes:
  - default: pretty-print the trace (rounds, votes, decision, outcome).
  - --rerun: re-run the same user_input through the live council and
    print the new decision next to the old one. Useful to spot-check
    whether vote-weight calibration has shifted reasoning.

Usage:
    python -m scripts.replay_trace <trace_id>
    python -m scripts.replay_trace <trace_id> --rerun
    python -m scripts.replay_trace --recent
    python -m scripts.replay_trace --fingerprint <fp>

This script is read-only when --rerun is omitted, so it's safe to point
at a production trace store.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

# Allow `python scripts/replay_trace.py` from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agi_runtime.cognition.trace import CouncilTrace, ThinkingTraceStore


def _format_vote_block(votes: dict) -> str:
    if not votes:
        return "  (no votes)"
    lines = []
    for name, v in sorted(votes.items()):
        marker = {"yes": "+", "no": "-", "abstain": "."}.get(v, "?")
        lines.append(f"  [{marker}] {name}: {v}")
    return "\n".join(lines)


def _print_trace(trace: CouncilTrace) -> None:
    print(f"trace_id      : {trace.trace_id}")
    print(f"fingerprint   : {trace.fingerprint or '(none)'}")
    print(f"created_at    : {trace.created_at}")
    print(f"updated_at    : {trace.updated_at}")
    print(f"outcome       : {trace.outcome or 'pending'}")
    print(f"user_input    :")
    for line in textwrap.wrap(trace.user_input or "", 76):
        print(f"  {line}")
    print()
    if trace.agent_weights_at_run:
        print("agent weights at run:")
        for name, w in sorted(trace.agent_weights_at_run.items()):
            print(f"  {name}: {w:.2f}")
        print()
    for r in trace.rounds:
        print(f"--round {r.round_index} {r.notes or ''}")
        if r.agent_outputs:
            for name, out in r.agent_outputs.items():
                snippet = (out or "").strip()
                if len(snippet) > 240:
                    snippet = snippet[:237] + "..."
                print(f"  {name}: {snippet}")
        if r.votes:
            print(_format_vote_block(r.votes))
        if r.critiques:
            print("  critiques:")
            for c in r.critiques:
                print(f"    - {c}")
        print()
    print(f"final decision: {trace.final_decision}")
    print(f"reasoning     : {trace.reasoning_summary}")


def _rerun(trace: CouncilTrace) -> None:
    """Re-deliberate the same input against the live council.

    Build the council from the same factory the agent uses so the rerun
    sees current weights, current breaker state, and current prompts.
    """
    try:
        import anthropic
    except Exception:
        print("[rerun] anthropic SDK not available — skipping rerun.")
        return
    from agi_runtime.cognition.system2 import make_default_roster
    from agi_runtime.cognition.system2.council import AgentCouncil
    from agi_runtime.cognition.system2.voting import VoteWeights

    client = anthropic.Anthropic()
    council = AgentCouncil(
        agents=make_default_roster(client),
        weights=VoteWeights(),
        max_rounds=2,
    )
    print("\n--live rerun ─────────────────────────────────────────")
    outcome = council.deliberate(
        user_input=trace.user_input, fingerprint=trace.fingerprint,
    )
    print(f"decision : {outcome.final_decision}")
    print(f"summary  : {outcome.reasoning_summary}")
    print(f"winner   : {outcome.vote.winner}  consensus={outcome.vote.consensus}")
    if outcome.final_decision == trace.final_decision:
        print("\n[match] live rerun matches the recorded decision.")
    else:
        print("\n[diff] decision drifted from the recorded trace.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("trace_id", nargs="?", help="trace id to replay")
    parser.add_argument(
        "--rerun", action="store_true",
        help="Re-deliberate this trace against the live council",
    )
    parser.add_argument(
        "--recent", action="store_true",
        help="List recent traces instead of replaying one",
    )
    parser.add_argument(
        "--fingerprint",
        help="List traces for a fingerprint (newest first)",
    )
    parser.add_argument(
        "--store", default="memory/cognition/traces",
        help="Trace store directory (default: memory/cognition/traces)",
    )
    args = parser.parse_args()

    store = ThinkingTraceStore(path=args.store)

    if args.recent or (not args.trace_id and not args.fingerprint):
        traces = store.find_recent(limit=20)
        if not traces:
            print("(no traces)")
            return 0
        for t in traces:
            print(
                f"{t.trace_id}  fp={t.fingerprint or '-':<20}  "
                f"outcome={t.outcome or 'pending':<8}  "
                f"rounds={len(t.rounds)}  "
                f"input={(t.user_input or '')[:60]}"
            )
        return 0

    if args.fingerprint:
        traces = store.find_by_fingerprint(args.fingerprint)
        if not traces:
            print(f"(no traces for fingerprint {args.fingerprint})")
            return 0
        for t in traces:
            print(
                f"{t.trace_id}  outcome={t.outcome or 'pending'}  "
                f"rounds={len(t.rounds)}"
            )
        return 0

    trace = store.get(args.trace_id)
    if trace is None:
        print(f"trace {args.trace_id!r} not found in {args.store}", file=sys.stderr)
        return 1

    _print_trace(trace)
    if args.rerun:
        _rerun(trace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
