from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from .models import DocketEntry


class StateStore:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS entries (
                docket_id INTEGER NOT NULL,
                entry_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                pdf_hash TEXT,
                ai_summarized INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (docket_id, entry_id))"""
        )
        self.db.commit()

    @staticmethod
    def fingerprint(entry: DocketEntry) -> str:
        data = {
            "description": entry.description,
            "modified": entry.date_modified,
            "documents": [
                {
                    "id": d.id,
                    "url": d.download_url,
                    "description": d.description,
                    "available": d.is_available,
                }
                for d in entry.documents
            ],
        }
        blob = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()

    def record(self, docket_id: int, entry_id: str) -> tuple | None:
        return self.db.execute(
            "SELECT fingerprint, pdf_hash, ai_summarized FROM entries WHERE docket_id=? AND entry_id=?",
            (docket_id, str(entry_id)),
        ).fetchone()

    def status(self, docket_id: int, entry: DocketEntry) -> str:
        row = self.record(docket_id, str(entry.id))
        if not row:
            return "new"
        return "changed" if row[0] != self.fingerprint(entry) else "unchanged"

    def needs_ai(self, docket_id: int, entry: DocketEntry, pdf_hash: str | None) -> bool:
        """True when this exact PDF has not been AI-summarized yet."""
        row = self.record(docket_id, str(entry.id))
        if not row:
            return True
        _, stored_hash, ai_done = row
        if not ai_done:
            return True
        return bool(pdf_hash) and stored_hash != pdf_hash

    def save(
        self,
        docket_id: int,
        entry: DocketEntry,
        notified: bool,
        pdf_hash: str | None = None,
        ai_summarized: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """INSERT INTO entries(docket_id, entry_id, fingerprint, pdf_hash,
                   ai_summarized, first_seen, last_seen, notified)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(docket_id, entry_id) DO UPDATE SET
                   fingerprint=excluded.fingerprint,
                   pdf_hash=COALESCE(excluded.pdf_hash, entries.pdf_hash),
                   ai_summarized=MAX(excluded.ai_summarized, entries.ai_summarized),
                   last_seen=excluded.last_seen,
                   notified=excluded.notified""",
            (docket_id, str(entry.id), self.fingerprint(entry), pdf_hash,
             int(ai_summarized), now, now, int(notified)),
        )
        self.db.commit()
