from datetime import date, timedelta

from docket_tracker.models import DocketEntry


TODAY = date(2026, 9, 23)


def test_august_entry_is_old():
    e = DocketEntry(1, "88", "2026-08-05", "ORDER")
    assert e.age_days(TODAY) == 49
    assert e.age_days(TODAY) > 21      # outside default window -> suppressed


def test_september_entry_is_recent():
    e = DocketEntry(1, "100", "2026-09-20", "ORDER")
    assert e.age_days(TODAY) == 3
    assert e.age_days(TODAY) <= 21     # inside window -> alerted


def test_unparseable_date_is_not_suppressed():
    e = DocketEntry(1, "x", "Unknown", "ORDER")
    assert e.filed_date() is None
    assert e.age_days(TODAY) is None   # None means "do not suppress"


def test_boundary_exactly_at_limit():
    e = DocketEntry(1, "99", (TODAY - timedelta(days=21)).isoformat(), "ORDER")
    assert e.age_days(TODAY) == 21
    assert not (e.age_days(TODAY) > 21)
