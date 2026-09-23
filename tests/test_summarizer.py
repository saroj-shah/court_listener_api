from docket_tracker.summarizer import verify

SOURCE = """[PAGE 1]
Defendants respectfully move this Court for a stay pending appeal of the
judgment entered on September 2, 2026.
"""


def test_grounded_point_kept():
    r = {"major_points": [{"point": "Seeks stay.",
                           "evidence": "Defendants respectfully move this Court for a stay"}]}
    filtered, ratio = verify(r, SOURCE)
    assert len(filtered["major_points"]) == 1 and ratio == 1.0


def test_hallucinated_point_dropped():
    r = {"major_points": [{"point": "Court granted it.",
                           "evidence": "the Court hereby grants the motion in full"}]}
    filtered, ratio = verify(r, SOURCE)
    assert filtered["major_points"] == [] and ratio == 0.0
