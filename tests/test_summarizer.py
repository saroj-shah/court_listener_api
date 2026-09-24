from docket_tracker.summarizer import verify

SOURCE = "[PAGE 1]\nDefendants respectfully move this Court for a stay pending appeal."


def test_grounded_kept():
    r = {"major_points": [{"point": "x", "evidence": "move this Court for a stay pending appeal"}]}
    filtered, ratio = verify(r, SOURCE)
    assert len(filtered["major_points"]) == 1 and ratio == 1.0


def test_hallucinated_dropped():
    r = {"major_points": [{"point": "x", "evidence": "the Court hereby grants the motion in full"}]}
    filtered, ratio = verify(r, SOURCE)
    assert filtered["major_points"] == [] and ratio == 0.0
