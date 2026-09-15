from docket_tracker.models import DocketEntry, Document
from docket_tracker.state import StateStore

def test_change_detection(tmp_path):
    s = StateStore(str(tmp_path / "x.db")); e = DocketEntry(1,"1","2026-01-01","Notice")
    assert s.status(7,e) == "new"; s.save(7,e,True); assert s.status(7,e) == "unchanged"
    e.documents.append(Document(9,"PDF",download_url="https://example.test/a.pdf"))
    assert s.status(7,e) == "changed"
