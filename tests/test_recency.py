from datetime import date, timedelta
from docket_tracker.models import DocketEntry

TODAY = date(2026, 9, 24)


def test_august_entry_is_old():
    assert DocketEntry(1, "88", "2026-08-05", "ORDER").age_days(TODAY) > 21


def test_september_entry_is_recent():
    assert DocketEntry(1, "100", "2026-09-20", "ORDER").age_days(TODAY) <= 21


def test_unparseable_date_not_suppressed():
    assert DocketEntry(1, "x", "Unknown", "ORDER").age_days(TODAY) is None


def test_boundary():
    d = (TODAY - timedelta(days=21)).isoformat()
    assert DocketEntry(1, "99", d, "ORDER").age_days(TODAY) == 21
