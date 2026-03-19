from pathlib import Path
import json


FAILURE_KINDS = {"deny", "failure"}


def replay_last_failure(
    journal_path: str = "memory/events.jsonl",
    *,
    context_before: int = 3,
    context_after: int = 1,
) -> dict:
    p = Path(journal_path)
    if not p.exists():
        return {"ok": False, "error": f"journal missing: {journal_path}"}

    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    events = []
    skipped_lines = 0
    for line_no, ln in enumerate(lines, start=1):
        try:
            event = json.loads(ln)
            event.setdefault("_line", line_no)
            events.append(event)
        except Exception:
            skipped_lines += 1
            continue

    failure_idx = None
    for i in range(len(events) - 1, -1, -1):
        if events[i].get("kind") in FAILURE_KINDS:
            failure_idx = i
            break

    if failure_idx is None:
        return {
            "ok": True,
            "message": "no failure events found",
            "parsed_events": len(events),
            "skipped_lines": skipped_lines,
        }

    start = max(0, failure_idx - max(0, context_before))
    end = min(len(events), failure_idx + 1 + max(0, context_after))
    context = events[start:end]
    failure = events[failure_idx]
    previous_input = None
    for i in range(failure_idx - 1, -1, -1):
        if events[i].get("kind") == "input":
            previous_input = events[i]
            break

    return {
        "ok": True,
        "failure_kind": failure.get("kind"),
        "failure": failure,
        "previous_input": previous_input,
        "context": context,
        "parsed_events": len(events),
        "skipped_lines": skipped_lines,
    }
