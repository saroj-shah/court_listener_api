import json

from docket_tracker.discord import DEFAULT_UPLOAD_LIMIT, build_payload, describe_pdf
from docket_tracker.models import Assessment, DocketEntry, Document, PdfStatus

CASE = {"short_name": "CLINIC v. Rubio",
        "docket_url": "https://www.courtlistener.com/docket/72218277/x/"}

A = Assessment("STAY_OR_INJUNCTION", "MEDIUM", "HIGH", "Motion to Stay",
               "Summary text.", ["point one"], "Why.", False, True,
               source="ai", grounding=1.0, model="m")
E = DocketEntry(1, "100", "2026-09-20", "MOTION to Stay", absolute_url="/docket/1/100/x/")


def test_small_pdf_is_attached():
    pdf = PdfStatus(PdfStatus.TEXT_READY, Document(1, "Motion"), data=b"%PDF-x",
                    text="t" * 500, pages=12, size=6, url="https://x/a.pdf", sha256="h")
    payload, blob, name = build_payload(CASE, E, A, "new", pdf)
    assert blob == b"%PDF-x" and name.endswith(".pdf")
    assert payload["attachments"][0]["filename"] == name


def test_oversized_pdf_falls_back_to_link():
    pdf = PdfStatus(PdfStatus.TEXT_READY, Document(1, "Motion"), data=b"x" * 100,
                    text="t" * 500, pages=900, size=50 * 1024 * 1024,
                    url="https://x/a.pdf", sha256="h")
    payload, blob, name = build_payload(CASE, E, A, "new", pdf)
    assert blob is None and name is None
    doc_field = [f for f in payload["embeds"][0]["fields"] if f["name"] == "Document"][0]
    assert "Too large to attach" in doc_field["value"]


def test_unavailable_pdf_is_stated_explicitly():
    pdf = PdfStatus(PdfStatus.NOT_AVAILABLE, Document(1, "Motion"), url="https://x/e/")
    payload, blob, _ = build_payload(CASE, E, A, "new", pdf)
    doc_field = [f for f in payload["embeds"][0]["fields"] if f["name"] == "Document"][0]
    assert "Not available" in doc_field["value"] and blob is None


def test_none_listed_is_stated():
    pdf = PdfStatus(PdfStatus.NONE_LISTED)
    payload, _, _ = build_payload(CASE, E, A, "new", pdf)
    doc_field = [f for f in payload["embeds"][0]["fields"] if f["name"] == "Document"][0]
    assert "no document attached" in doc_field["value"].lower()


def test_scanned_is_stated():
    pdf = PdfStatus(PdfStatus.SCANNED, Document(1, "Order"), data=b"%PDF",
                    pages=3, size=4, url="https://x/a.pdf")
    text = describe_pdf(pdf, True, DEFAULT_UPLOAD_LIMIT)
    assert "scanned" in text.lower() and "not summarized" in text.lower()


def test_field_limits_respected():
    pdf = PdfStatus(PdfStatus.TEXT_READY, Document(1, "M"), data=b"x", text="t" * 500,
                    pages=1, size=1, url="https://x/a.pdf")
    big = Assessment("DECISION_OR_ORDER", "HIGH", "HIGH", "Order", "s" * 5000,
                     ["p" * 3000], "w" * 3000, True, False)
    payload, _, _ = build_payload(CASE, E, big, "new", pdf)
    for field in payload["embeds"][0]["fields"]:
        assert len(field["value"]) <= 1024, field["name"]
    assert payload["content"] == "@here"
