from pathlib import Path
import json


def replay_last_failure(journal_path: str = "memory/events.jsonl") -> dict:
    p = Path(journal_path)
    if not p.exists():
        return {"ok": False, "error": f"journal missing: {journal_path}"}

    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    events = []
    for ln in lines:
        try:
            events.append(json.loads(ln))
        except Exception:
            continue

    # treat deny events as failures for now
    failure_idx = None
    for i in range(len(events) - 1, -1, -1):
        if events[i].get("kind") in {"deny", "failure"}:
            failure_idx = i
            break

    if failure_idx is None:
        return {"ok": True, "message": "no failure events found"}

    start = max(0, failure_idx - 3)
    context = events[start : failure_idx + 1]
    return {
        "ok": True,
        "failure_kind": events[failure_idx].get("kind"),
        "context": context,
    }
