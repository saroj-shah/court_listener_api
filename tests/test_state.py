from docket_tracker.models import DocketEntry, Document
from docket_tracker.state import StateStore


def test_change_and_ai_tracking(tmp_path):
    store = StateStore(str(tmp_path / "t.db"))
    e = DocketEntry(1, "1", "2026-01-01", "Notice")

    assert store.status(7, e) == "new"
    store.save(7, e, notified=True, pdf_hash=None, ai_summarized=False)
    assert store.status(7, e) == "unchanged"

    # PDF attached later -> changed
    e.documents.append(Document(9, "PDF", download_url="/x.pdf", is_available=True))
    assert store.status(7, e) == "changed"

    # AI runs once, then is skipped for the same PDF hash
    assert store.needs_ai(7, e, "hash-a") is True
    store.save(7, e, notified=True, pdf_hash="hash-a", ai_summarized=True)
    assert store.needs_ai(7, e, "hash-a") is False
    assert store.needs_ai(7, e, "hash-b") is True
