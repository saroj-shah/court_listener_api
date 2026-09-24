from docket_tracker.discord import DEFAULT_UPLOAD_LIMIT, build_payload, describe_pdf
from docket_tracker.models import Assessment, DocketEntry, Document, PdfStatus

CASE = {"short_name": "CLINIC v. Rubio",
        "docket_url": "https://www.courtlistener.com/docket/72218277/x/"}
A = Assessment("STAY_OR_INJUNCTION", "MEDIUM", "HIGH", "Motion to Stay",
               "Summary.", ["point"], "Why.", False, True, source="ai",
               grounding=1.0, model="m")
E = DocketEntry(1, "100", "2026-09-20", "MOTION to Stay", absolute_url="/docket/1/100/x/")


def _doc_field(payload):
    return [f for f in payload["embeds"][0]["fields"] if f["name"] == "Document"][0]["value"]


def test_small_pdf_attached():
    pdf = PdfStatus(PdfStatus.TEXT_READY, Document(1, "Motion"), data=b"%PDF-x",
                    text="t" * 500, pages=12, size=6, url="https://x/a.pdf", sha256="h")
    payload, blob, name = build_payload(CASE, E, A, "new", pdf)
    assert blob == b"%PDF-x" and name.endswith(".pdf")


def test_oversized_falls_back_to_link():
    pdf = PdfStatus(PdfStatus.TEXT_READY, Document(1, "Motion"), data=b"x" * 10,
                    text="t" * 500, pages=900, size=50 * 1024 * 1024, url="https://x/a.pdf")
    payload, blob, name = build_payload(CASE, E, A, "new", pdf)
    assert blob is None and "Too large to attach" in _doc_field(payload)


def test_download_failed_message_is_actionable():
    pdf = PdfStatus(PdfStatus.DOWNLOAD_FAILED, Document(1, "Motion"), url="https://x/a.pdf")
    payload, blob, _ = build_payload(CASE, E, A, "new", pdf)
    value = _doc_field(payload)
    assert "Could not download" in value and "Open PDF manually" in value and blob is None


def test_not_available_stated():
    payload, _, _ = build_payload(CASE, E, A, "new", PdfStatus(PdfStatus.NOT_AVAILABLE))
    assert "Not available" in _doc_field(payload)


def test_none_listed_stated():
    payload, _, _ = build_payload(CASE, E, A, "new", PdfStatus(PdfStatus.NONE_LISTED))
    assert "no document attached" in _doc_field(payload).lower()


def test_scanned_stated():
    pdf = PdfStatus(PdfStatus.SCANNED, Document(1, "Order"), data=b"%PDF", pages=3, size=4)
    assert "scanned" in describe_pdf(pdf, True, DEFAULT_UPLOAD_LIMIT).lower()


def test_field_limits_and_here():
    pdf = PdfStatus(PdfStatus.TEXT_READY, Document(1, "M"), data=b"x", text="t" * 500,
                    pages=1, size=1, url="https://x/a.pdf")
    big = Assessment("DECISION_OR_ORDER", "HIGH", "HIGH", "Order", "s" * 5000,
                     ["p" * 3000], "w" * 3000, True, False)
    payload, _, _ = build_payload(CASE, E, big, "new", pdf)
    for f in payload["embeds"][0]["fields"]:
        assert len(f["value"]) <= 1024, f["name"]
    assert payload["content"] == "@here"


def test_party_filing_never_gets_here():
    payload, _, _ = build_payload(CASE, E, A, "new", PdfStatus(PdfStatus.NONE_LISTED))
    assert payload["content"] == ""
    posture = [f for f in payload["embeds"][0]["fields"] if f["name"] == "Posture"][0]
    assert "not a ruling" in posture["value"]
