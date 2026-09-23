from docket_tracker.models import Document, PdfStatus
from docket_tracker.pdf_extractor import is_scanned, pick_document, safe_filename


def test_no_documents():
    doc, state = pick_document([])
    assert doc is None and state == PdfStatus.NONE_LISTED


def test_listed_but_not_in_recap():
    docs = [Document(1, "Motion", is_available=False, download_url=None)]
    doc, state = pick_document(docs)
    assert state == PdfStatus.NOT_AVAILABLE and doc is not None


def test_picks_longest_available():
    docs = [
        Document(1, "Exhibit", download_url="/a.pdf", is_available=True, page_count=2),
        Document(2, "Motion", download_url="/b.pdf", is_available=True, page_count=30),
    ]
    doc, state = pick_document(docs)
    assert doc.id == 2 and state == "available"


def test_scanned_detection():
    assert is_scanned("", 10) is True
    assert is_scanned("x" * 5000, 10) is False


def test_filename_is_safe():
    name = safe_filename("100", "MOTION to Stay / Pending Appeal!!")
    assert name.endswith(".pdf") and "/" not in name
    assert name.startswith("entry-100-")
