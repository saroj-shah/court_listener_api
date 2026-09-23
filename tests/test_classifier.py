from docket_tracker.classifier import assess, from_ai
from docket_tracker.models import DocketEntry, PdfStatus


def entry(text):
    return DocketEntry(1, "100", "2026-09-20", text)


def test_motion_to_stay_is_medium():
    a = assess(entry("MOTION to Stay pending appeal filed by Defendants"))
    assert a.impact == "MEDIUM" and a.party_request and not a.court_decision


def test_order_denying_stay_is_high():
    a = assess(entry("ORDER: The motion is denied. SO ORDERED."))
    assert a.impact == "HIGH" and a.court_decision


def test_appearance_is_low():
    assert assess(entry("NOTICE OF APPEARANCE by counsel")).impact == "LOW"


def test_pdf_state_appears_in_points():
    a = assess(entry("NOTICE OF APPEARANCE"), PdfStatus(PdfStatus.NOT_AVAILABLE))
    assert any("RECAP" in p for p in a.major_points)


def test_ai_result_maps():
    result = {
        "document_type": "Motion to Stay", "classification": "STAY_OR_INJUNCTION",
        "impact": "MEDIUM", "confidence": "HIGH",
        "short_description": "Seeks a stay.",
        "major_points": [{"point": "Seeks a stay.", "evidence": "move for a stay"}],
        "why_it_matters": "May pause implementation.", "deadlines": [],
        "court_decision": False, "party_request": True,
        "_grounding_ratio": 1.0, "_model": "m",
    }
    a = from_ai(result, entry("MOTION"))
    assert a.source == "ai" and a.major_points == ["Seeks a stay."]
