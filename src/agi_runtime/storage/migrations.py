from pathlib import Path
import sqlite3
import time


class MigrationRunner:
    def __init__(self, db_path: str, migrations_dir: str):
        self.db_path = db_path
        self.migrations_dir = Path(migrations_dir)

    def run(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
            )
            conn.commit()

            files = sorted(self.migrations_dir.glob("*.sql"))
            for f in files:
                version = f.stem
                cur = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,))
                if cur.fetchone():
                    continue
                sql = f.read_text()
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                    (version, int(time.time())),
                )
                conn.commit()
        finally:
            conn.close()
