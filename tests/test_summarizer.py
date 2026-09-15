from docket_tracker.summarizer import verify

SOURCE = """[PAGE 1]
Defendants respectfully move this Court for a stay pending appeal of the
judgment entered on September 2, 2026. The Department of State has ceased
applying the January 14, 2026 guidance.
"""


def test_grounded_point_is_kept():
    result = {"major_points": [
        {"point": "Government seeks a stay.",
         "evidence": "Defendants respectfully move this Court for a stay pending appeal"},
    ]}
    filtered, ratio = verify(result, SOURCE)
    assert len(filtered["major_points"]) == 1 and ratio == 1.0


def test_hallucinated_point_is_dropped():
    result = {"major_points": [
        {"point": "Court granted the stay.",
         "evidence": "the Court hereby grants the motion for a stay in full"},
    ]}
    filtered, ratio = verify(result, SOURCE)
    assert filtered["major_points"] == [] and ratio == 0.0


def test_mixed_points_partially_kept():
    result = {"major_points": [
        {"point": "Seeks stay.", "evidence": "move this Court for a stay pending appeal"},
        {"point": "Fabricated.", "evidence": "sanctions were imposed on plaintiffs counsel"},
    ]}
    filtered, ratio = verify(result, SOURCE)
    assert len(filtered["major_points"]) == 1 and ratio == 0.5
