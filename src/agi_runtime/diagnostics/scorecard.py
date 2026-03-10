from dataclasses import dataclass, asdict
from pathlib import Path
import json
import sqlite3


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _load_json(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _check_db(db_path: str) -> Check:
    p = Path(db_path)
    if not p.exists():
        return Check("database", False, f"missing: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("SELECT 1 FROM schema_migrations LIMIT 1").fetchone()
            conn.execute("SELECT 1 FROM sessions LIMIT 1").fetchone()
            conn.execute("SELECT 1 FROM tasks LIMIT 1").fetchone()
        finally:
            conn.close()
        return Check("database", True, "sqlite + migrations present")
    except Exception as e:
        return Check("database", False, f"db check failed: {e}")


def run_scorecard(config_path: str = "helloagi.json", onboard_path: str = "helloagi.onboard.json") -> dict:
    checks: list[Check] = []

    cfg = _load_json(config_path)
    if cfg is None:
        checks.append(Check("config", False, f"missing/invalid: {config_path}"))
        db_path = "memory/helloagi.db"
        journal_path = "memory/events.jsonl"
    else:
        checks.append(Check("config", True, "ok"))
        db_path = cfg.get("db_path", "memory/helloagi.db")
        journal_path = cfg.get("journal_path", "memory/events.jsonl")

    onboard = _load_json(onboard_path)
    checks.append(Check("onboarding", onboard is not None, "ok" if onboard else f"missing: {onboard_path}"))

    checks.append(_check_db(db_path))

    j = Path(journal_path)
    checks.append(Check("journal", j.exists(), "ok" if j.exists() else f"missing: {journal_path}"))

    passed = sum(1 for c in checks if c.ok)
    total = len(checks)
    grade = round((passed / total) * 100) if total else 0

    return {
        "grade": grade,
        "passed": passed,
        "total": total,
        "checks": [asdict(c) for c in checks],
    }
