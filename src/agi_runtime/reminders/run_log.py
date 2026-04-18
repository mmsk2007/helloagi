from __future__ import annotations

import json
import time
from pathlib import Path


class ReminderRunLog:
    def __init__(self, path: str = "memory/reminder_runs.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, job_id: str, status: str, *, detail: str = "") -> None:
        row = {
            "ts": time.time(),
            "job_id": job_id,
            "status": status,
            "detail": detail[:500],
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

