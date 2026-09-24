"""The 403 fix: RECAP paths must resolve to storage.courtlistener.com first."""
from docket_tracker.models import Document, PdfStatus
from docket_tracker.pdf_extractor import candidate_urls, pick_document, safe_filename


def test_bare_recap_path_prefers_storage_host():
    urls = candidate_urls("recap/gov.uscourts.nysd.657161/gov.uscourts.nysd.657161.87.0.pdf")
    assert urls[0].startswith("https://storage.courtlistener.com/recap/")
    assert urls[1].startswith("https://www.courtlistener.com/recap/")


def test_leading_slash_handled():
    urls = candidate_urls("/recap/x/y.pdf")
    assert urls[0] == "https://storage.courtlistener.com/recap/x/y.pdf"


def test_www_absolute_url_gets_storage_fallback():
    urls = candidate_urls("https://www.courtlistener.com/recap/x/y.pdf")
    assert len(urls) == 2
    assert urls[1] == "https://storage.courtlistener.com/recap/x/y.pdf"


def test_empty_returns_nothing():
    assert candidate_urls(None) == [] and candidate_urls("") == []


def test_filename_accepts_int_description():
    # This is the crash: description came back as an int from the API.
    name = safe_filename(100, 12345)
    assert name.endswith(".pdf") and name.startswith("entry-100-")


def test_filename_accepts_none():
    assert safe_filename(None, None) == "entry-unknown-document.pdf"


def test_filename_sanitizes_slashes():
    name = safe_filename("91", "MOTION to Stay / Pending Appeal!!")
    assert "/" not in name and name.startswith("entry-91-")


def test_pick_document_states():
    assert pick_document([])[1] == PdfStatus.NONE_LISTED
    assert pick_document([Document(1, "M", is_available=False)])[1] == PdfStatus.NOT_AVAILABLE
    docs = [Document(1, "Ex", download_url="/a.pdf", is_available=True, page_count=2),
            Document(2, "Mot", download_url="/b.pdf", is_available=True, page_count=30)]
    doc, state = pick_document(docs)
    assert doc.id == 2 and state == "available"
