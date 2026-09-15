from docket_tracker.classifier import assess
from docket_tracker.models import DocketEntry

def entry(text): return DocketEntry(1, "100", "2026-09-14", text)

def test_motion_is_medium_not_decision():
    a = assess(entry("MOTION to Stay pending appeal filed by Defendants"))
    assert a.impact == "MEDIUM" and a.party_request and not a.court_decision

def test_stay_denied_order_is_high():
    a = assess(entry("ORDER: Motion to stay is denied."))
    assert a.impact == "HIGH" and a.court_decision

def test_appearance_is_low():
    assert assess(entry("NOTICE OF APPEARANCE")).impact == "LOW"
