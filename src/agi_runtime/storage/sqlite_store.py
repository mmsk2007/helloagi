from __future__ import annotations

import sqlite3
import time
import uuid


class SQLiteStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def create_session(self, owner_name: str = "") -> str:
        sid = str(uuid.uuid4())
        now = int(time.time())
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO sessions(id, owner_name, created_at) VALUES(?,?,?)",
                (sid, owner_name, now),
            )
            conn.commit()
            return sid
        finally:
            conn.close()

    def create_task(self, session_id: str, title: str, status: str = "pending") -> str:
        tid = str(uuid.uuid4())
        now = int(time.time())
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO tasks(id, session_id, title, status, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                (tid, session_id, title, status, now, now),
            )
            conn.commit()
            return tid
        finally:
            conn.close()

    def update_task_status(self, task_id: str, status: str):
        now = int(time.time())
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                (status, now, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tasks(self, session_id: str) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, title, status, created_at, updated_at FROM tasks WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "title": r[1],
                    "status": r[2],
                    "created_at": r[3],
                    "updated_at": r[4],
                }
                for r in rows
            ]
        finally:
            conn.close()
