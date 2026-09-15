from __future__ import annotations
import hashlib, json, sqlite3
from datetime import datetime, timezone
from .models import DocketEntry

class StateStore:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS entries (
            docket_id INTEGER NOT NULL, entry_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, notified INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (docket_id, entry_id))""")
        self.db.commit()

    @staticmethod
    def fingerprint(entry: DocketEntry) -> str:
        data = {"description": entry.description, "modified": entry.date_modified,
                "documents": [{"id": d.id, "url": d.download_url, "description": d.description} for d in entry.documents]}
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def status(self, docket_id: int, entry: DocketEntry) -> str:
        row = self.db.execute("SELECT fingerprint FROM entries WHERE docket_id=? AND entry_id=?", (docket_id, str(entry.id))).fetchone()
        if not row:
            return "new"
        return "changed" if row[0] != self.fingerprint(entry) else "unchanged"

    def save(self, docket_id: int, entry: DocketEntry, notified: bool):
        now = datetime.now(timezone.utc).isoformat()
        fp = self.fingerprint(entry)
        self.db.execute("""INSERT INTO entries(docket_id,entry_id,fingerprint,first_seen,last_seen,notified)
          VALUES(?,?,?,?,?,?) ON CONFLICT(docket_id,entry_id) DO UPDATE SET
          fingerprint=excluded.fingerprint,last_seen=excluded.last_seen,notified=excluded.notified""",
          (docket_id, str(entry.id), fp, now, now, int(notified)))
        self.db.commit()
