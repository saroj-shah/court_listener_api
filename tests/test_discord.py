import json

from docket_tracker.discord import build_payload
from docket_tracker.models import Assessment, DocketEntry

CASE = {"short_name": "CLINIC v. Rubio",
        "docket_url": "https://www.courtlistener.com/docket/72218277/x/"}


def test_payload_within_discord_limits():
    entry = DocketEntry(1, "100", "2026-09-14", "MOTION to Stay", absolute_url="/docket/1/100/x/")
    a = Assessment("STAY_OR_INJUNCTION", "MEDIUM", "HIGH", "Motion to Stay",
                   "x" * 5000, ["p" * 3000], "y" * 3000, False, True,
                   source="ai", grounding=1.0, model="m")
    payload = build_payload(CASE, entry, a, "new")
    embed = payload["embeds"][0]
    assert len(embed["title"]) <= 256
    for field in embed["fields"]:
        assert len(field["value"]) <= 1024, field["name"]
    assert len(json.dumps(payload)) < 6000
    assert payload["content"] == ""  # no @here for a party motion


def test_here_only_for_high_court_decision():
    entry = DocketEntry(1, "101", "2026-09-15", "ORDER")
    a = Assessment("DECISION_OR_ORDER", "HIGH", "HIGH", "Order", "s", ["p"], "w", True, False)
    assert build_payload(CASE, entry, a, "new")["content"] == "@here"
