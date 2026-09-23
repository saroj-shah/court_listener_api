import sqlite3

from docket_tracker.models import DocketEntry, Document
from docket_tracker.state import StateStore


def test_change_and_ai_tracking(tmp_path):
    store = StateStore(str(tmp_path / "t.db"))
    e = DocketEntry(1, "1", "2026-09-20", "Notice")
    assert store.status(7, e) == "new"
    store.save(7, e, notified=True)
    assert store.status(7, e) == "unchanged"
    e.documents.append(Document(9, "PDF", download_url="/x.pdf", is_available=True))
    assert store.status(7, e) == "changed"
    assert store.needs_ai(7, e, "hash-a") is True
    store.save(7, e, True, pdf_hash="hash-a", ai_summarized=True)
    assert store.needs_ai(7, e, "hash-a") is False


def test_v1_database_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE entries (docket_id INTEGER, entry_id TEXT,
        fingerprint TEXT, first_seen TEXT, last_seen TEXT, notified INTEGER,
        PRIMARY KEY(docket_id, entry_id))""")
    db.execute("INSERT INTO entries VALUES (1,'5','fp','t','t',1)")
    db.commit()
    db.close()

    store = StateStore(path)   # must not raise
    cols = {row[1] for row in store.db.execute("PRAGMA table_info(entries)")}
    assert {"pdf_hash", "ai_summarized", "date_filed", "pdf_state"} <= cols
    assert store.is_known(1, "5")   # existing row preserved
