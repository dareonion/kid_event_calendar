from datetime import datetime
from zoneinfo import ZoneInfo

from kid_events.models import AgeBand
from kid_events.sources.activecommunities import (
    age_range_to_bands,
    bands_for_item,
    parse_activities,
)

ET = ZoneInfo("America/Toronto")
PT = ZoneInfo("America/Los_Angeles")
WIN_START = datetime(2026, 7, 6, tzinfo=PT)  # a Monday
WIN_END = datetime(2026, 7, 19, tzinfo=PT)  # the following Sunday


def _activity(**over: object) -> dict:
    base = {
        "id": 100,
        "name": "Baby Storytime",
        "desc": "<p>Songs &amp; rhymes</p>",
        "detail_url": "https://example.org/activity/100",
        "days_of_week": "Mon",
        "date_range_start": "2026-07-06",
        "date_range_end": "2026-08-10",
        "time_range": "1:30 PM - 2:15 PM",
        "only_one_day": False,
        "allow_drop_in_reg": False,
        "age_min_year": 0,
        "age_min_month": 0,
        "age_max_year": 1,
        "age_max_month": 6,
        "location": {"label": "Burnhamthorpe Library"},
    }
    base.update(over)
    return base


def _parse(item: dict) -> list:
    return parse_activities(
        [item],
        key="mississauga",
        name="Mississauga Library",
        default_city="mississauga",
        tz=ET,
        window_start=WIN_START,
        window_end=WIN_END,
    )


def test_weekly_activity_expands_to_in_window_occurrences():
    events = _parse(_activity())
    # Mondays in [Jul 6, Jul 19]: Jul 6 and Jul 13.
    assert [e.start.date().isoformat() for e in events] == ["2026-07-06", "2026-07-13"]
    e = events[0]
    assert e.start == datetime(2026, 7, 6, 13, 30, tzinfo=ET)  # Eastern, 1:30 PM
    assert e.end == datetime(2026, 7, 6, 14, 15, tzinfo=ET)
    # 0y0m..1y6m (18 mo) straddles the infant/toddler boundary.
    assert e.age_bands == [AgeBand.INFANT, AgeBand.TODDLER]
    assert e.location_name == "Burnhamthorpe Library"
    assert e.registration_required is True
    assert "Songs" in e.description  # html stripped
    assert e.id == "mississauga:100:2026-07-06"


def test_all_ages_sentinel_and_age_range():
    all_ages = _parse(_activity(age_max_year=0, age_max_month=0))
    assert all_ages[0].age_bands == [AgeBand.ALL_AGES]

    school_teen = _parse(
        _activity(age_min_year=8, age_min_month=0, age_max_year=13, age_max_month=0)
    )
    assert set(school_teen[0].age_bands) == {AgeBand.SCHOOL_AGE, AgeBand.TWEEN_TEEN}


def test_adult_only_activity_is_dropped():
    # 25y+ overlaps no kid band, so it yields no events at all.
    adult = _parse(_activity(age_min_year=25, age_min_month=0, age_max_year=99, age_max_month=0))
    assert adult == []


def test_only_one_day_activity():
    once = _parse(_activity(only_one_day=True, days_of_week="", date_range_start="2026-07-08"))
    assert [e.start.date().isoformat() for e in once] == ["2026-07-08"]


def test_age_range_to_bands_overlap():
    assert age_range_to_bands(0, 17) == {AgeBand.INFANT}
    assert AgeBand.ALL_AGES not in age_range_to_bands(0, 1200)
    assert bands_for_item({"age_min_year": 0, "age_max_year": 0}) == [AgeBand.ALL_AGES]
