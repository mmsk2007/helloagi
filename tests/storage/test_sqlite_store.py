import unittest
import tempfile
from pathlib import Path

from agi_runtime.storage.migrations import MigrationRunner
from agi_runtime.storage.sqlite_store import SQLiteStore


class TestSQLiteStore(unittest.TestCase):
    def test_session_task_flow(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "helloagi.db")
            migrations = str(Path("src/agi_runtime/storage/migrations"))
            MigrationRunner(db, migrations).run()
            s = SQLiteStore(db)
            sid = s.create_session("owner")
            tid = s.create_task(sid, "task one")
            s.update_task_status(tid, "done")
            tasks = s.list_tasks(sid)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["status"], "done")


if __name__ == '__main__':
    unittest.main()
