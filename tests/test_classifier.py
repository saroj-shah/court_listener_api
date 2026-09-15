from docket_tracker.classifier import assess, from_ai
from docket_tracker.models import DocketEntry


def entry(text):
    return DocketEntry(1, "100", "2026-09-14", text)


def test_motion_to_stay_is_medium_not_high():
    a = assess(entry("MOTION to Stay pending appeal filed by Defendants"))
    assert a.impact == "MEDIUM"
    assert a.party_request and not a.court_decision


def test_order_denying_stay_is_high():
    a = assess(entry("ORDER: The motion is denied. SO ORDERED."))
    assert a.impact == "HIGH" and a.court_decision


def test_appearance_is_low():
    assert assess(entry("NOTICE OF APPEARANCE by counsel")).impact == "LOW"


def test_ai_result_maps_to_assessment():
    result = {
        "document_type": "Motion to Stay",
        "classification": "STAY_OR_INJUNCTION",
        "impact": "MEDIUM",
        "confidence": "HIGH",
        "short_description": "The government seeks a stay pending appeal.",
        "major_points": [{"point": "Seeks a stay.", "evidence": "defendants respectfully move for a stay"}],
        "why_it_matters": "Could pause implementation.",
        "deadlines": [],
        "court_decision": False,
        "party_request": True,
        "_grounding_ratio": 1.0,
        "_model": "test-model",
    }
    a = from_ai(result, entry("MOTION to Stay"))
    assert a.source == "ai" and a.major_points == ["Seeks a stay."]
