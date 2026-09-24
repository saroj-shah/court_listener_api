"""Regression tests for the bug where party filings were labelled 'Court decision'."""
from docket_tracker.classifier import assess, detect_posture
from docket_tracker.models import DocketEntry


def e(text, num="100"):
    return DocketEntry(1, num, "2026-09-20", text)


def test_emergency_motion_citing_an_opinion_is_a_party_filing():
    # This is the exact Entry 85 text that was misclassified as a court decision.
    text = ("EMERGENCY MOTION to Enforce Judgment re: 83 Memorandum & Opinion, "
            "84 Clerk's Judgment. Document filed by African Communities Together")
    court, party = detect_posture(text)
    assert court is False and party is True
    assert assess(e(text)).court_decision is False


def test_response_to_motion_is_party_filing():
    text = ("RESPONSE to Motion re: 85 EMERGENCY MOTION to Enforce Judgment re: 83 "
            "Memorandum & Opinion. Document filed by Marco Rubio")
    assert detect_posture(text) == (False, True)


def test_reply_memorandum_is_party_filing():
    text = "REPLY MEMORANDUM OF LAW in Support re: 85 EMERGENCY MOTION to Enforce Judgment"
    assert detect_posture(text) == (False, True)


def test_reply_affidavit_is_party_filing():
    text = "REPLY AFFIDAVIT of Agnes Kyeremaa in Support re: 85 EMERGENCY MOTION"
    assert detect_posture(text) == (False, True)


def test_consent_letter_motion_is_party_filing():
    text = "CONSENT LETTER MOTION for Conference addressed to Judge Vargas from Counsel"
    assert detect_posture(text) == (False, True)


def test_actual_order_is_court_decision():
    text = ("ORDER: Defendants' response shall be due by 5:00 pm on Friday, "
            "August 28, 2026. SO ORDERED. (Signed by Judge Jeannette A. Vargas)")
    court, party = detect_posture(text)
    assert court is True and party is False
    assert assess(e(text)).court_decision is True


def test_opinion_and_order_is_court_decision():
    text = "OPINION AND ORDER re: 47 MOTION for Summary Judgment. GRANTED IN PART"
    assert detect_posture(text)[0] is True
    assert assess(e(text)).impact == "HIGH"


def test_clerks_judgment_is_court_decision():
    text = "CLERK'S RULE 54(b) JUDGMENT re: 83 Opinion & Order. ORDERED, ADJUDGED AND DECREED"
    assert detect_posture(text)[0] is True


def test_order_granting_letter_motion_is_court_decision():
    text = "ORDER granting 88 Letter Motion for Conference. HEREBY ORDERED by Judge Vargas"
    assert detect_posture(text) == (True, False)


def test_notice_of_appearance_is_low_and_party():
    a = assess(e("NOTICE OF APPEARANCE by Baher Azmy on behalf of plaintiffs"))
    assert a.impact == "LOW" and a.court_decision is False
