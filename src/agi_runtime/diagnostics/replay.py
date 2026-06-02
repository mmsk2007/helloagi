from pathlib import Path
import json


FAILURE_KINDS = {"deny", "failure"}
CONTEXT_WORKSPACE_KIND = "context_workspace_tool_evidence"


def _summarize_context_workspace(event: dict | None) -> dict | None:
    """Return a compact, user-auditable summary of a context workspace event."""
    if not event:
        return None
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    workspace = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else None
    if workspace is None or not isinstance(workspace.get("items"), list):
        return None
    items = workspace["items"]
    item_types = sorted({str(item.get("type")) for item in items if isinstance(item, dict) and item.get("type")})
    observed = 0
    generated = 0
    verified = 0
    unverified_generated = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        is_observed = bool(item.get("observed"))
        is_verified = bool(item.get("verified"))
        if is_observed:
            observed += 1
        else:
            generated += 1
        if is_verified:
            verified += 1
        if not is_observed and not is_verified:
            unverified_generated += 1
    return {
        "tool": payload.get("tool"),
        "action_ready": payload.get("action_ready"),
        "line": event.get("_line"),
        "summary": {
            "items": len(items),
            "observed": observed,
            "generated": generated,
            "verified": verified,
            "unverified_generated": unverified_generated,
            "item_types": item_types,
        },
    }


def _short_text(value: object, *, limit: int = 160) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def format_replay_report(report: dict) -> str:
    """Render replay diagnostics as concise human-readable text."""
    if not report.get("ok"):
        return f"Replay failed: {report.get('error', 'unknown error')}"
    if report.get("message"):
        lines = [str(report["message"])]
        lines.append(f"Parsed events: {report.get('parsed_events', 0)}")
        skipped = report.get("skipped_lines", 0)
        if skipped:
            lines.append(f"Skipped malformed lines: {skipped}")
        return "\n".join(lines)

    failure = report.get("failure") if isinstance(report.get("failure"), dict) else {}
    previous_input = report.get("previous_input") if isinstance(report.get("previous_input"), dict) else None
    workspace = report.get("latest_context_workspace")
    lines = [
        f"Last failure: {report.get('failure_kind', 'unknown')} at journal line {failure.get('_line', 'unknown')}",
        f"Parsed events: {report.get('parsed_events', 0)}",
    ]
    skipped = report.get("skipped_lines", 0)
    if skipped:
        lines.append(f"Skipped malformed lines: {skipped}")
    if previous_input:
        payload = previous_input.get("payload") if isinstance(previous_input.get("payload"), dict) else {}
        text = payload.get("text") or payload.get("message") or payload.get("prompt") or ""
        if text:
            lines.append(f"Previous input: {_short_text(text)}")
    if isinstance(workspace, dict):
        summary = workspace.get("summary") if isinstance(workspace.get("summary"), dict) else {}
        item_types = summary.get("item_types") if isinstance(summary.get("item_types"), list) else []
        action_ready = workspace.get("action_ready")
        if action_ready is True:
            action_ready_text = "yes"
        elif action_ready is False:
            action_ready_text = "no"
        else:
            action_ready_text = "unknown"
        lines.extend(
            [
                "Context workspace evidence:",
                f"  tool: {workspace.get('tool') or 'unknown'}",
                f"  journal line: {workspace.get('line') or 'unknown'}",
                f"  action ready: {action_ready_text}",
                "  items: "
                f"{summary.get('items', 0)} "
                f"(observed {summary.get('observed', 0)}, "
                f"generated {summary.get('generated', 0)}, "
                f"verified {summary.get('verified', 0)})",
                f"  unverified generated: {summary.get('unverified_generated', 0)}",
                f"  item types: {', '.join(str(item_type) for item_type in item_types) if item_types else 'none'}",
            ]
        )
    return "\n".join(lines)


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
    latest_context_workspace = None
    for i in range(failure_idx - 1, -1, -1):
        if previous_input is None and events[i].get("kind") == "input":
            previous_input = events[i]
        if latest_context_workspace is None and events[i].get("kind") == CONTEXT_WORKSPACE_KIND:
            latest_context_workspace = _summarize_context_workspace(events[i])
        if previous_input is not None and latest_context_workspace is not None:
            break

    return {
        "ok": True,
        "failure_kind": failure.get("kind"),
        "failure": failure,
        "previous_input": previous_input,
        "latest_context_workspace": latest_context_workspace,
        "context": context,
        "parsed_events": len(events),
        "skipped_lines": skipped_lines,
    }
