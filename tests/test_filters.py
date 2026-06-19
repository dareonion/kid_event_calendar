from datetime import datetime
from zoneinfo import ZoneInfo

from kid_events.filters import FilterParams, SortKey, apply_filters
from kid_events.models import AgeBand, Event

PT = ZoneInfo("America/Los_Angeles")


def _event(eid, bands, *, miles=None, day=20, title="Event", desc="", source="a"):
    return Event(
        id=eid,
        source=source,
        source_key=source,
        title=title,
        description=desc,
        start=datetime(2026, 6, day, 10, 0, tzinfo=PT),
        age_bands=list(bands),
        distance_mi=miles,
    )


EVENTS = [
    _event("infant", [AgeBand.INFANT], miles=3, title="Baby Storytime"),
    _event("toddler", [AgeBand.TODDLER], miles=8, title="Toddler Dance"),
    _event("school", [AgeBand.SCHOOL_AGE], miles=15, title="LEGO Club"),
    _event("family", [AgeBand.ALL_AGES], miles=25, title="Family Movie"),
    _event("online", [AgeBand.INFANT], miles=None, title="Virtual Sing-along"),
]


def test_child_age_selects_overlapping_bands():
    out = apply_filters(EVENTS, FilterParams(child_age_months=8))
    ids = {e.id for e in out}
    assert ids == {"infant", "family", "online"}  # infant + all_ages bands


def test_explicit_age_bands():
    out = apply_filters(EVENTS, FilterParams(age_bands={AgeBand.SCHOOL_AGE}))
    assert {e.id for e in out} == {"school"}


def test_no_age_filter_returns_all():
    out = apply_filters(EVENTS, FilterParams())
    assert len(out) == len(EVENTS)


def test_distance_filter_and_unknown_toggle():
    near = apply_filters(EVENTS, FilterParams(max_miles=10))
    assert {e.id for e in near} == {"infant", "toddler", "online"}  # online unknown kept

    near_strict = apply_filters(
        EVENTS, FilterParams(max_miles=10, include_unknown_location=False)
    )
    assert {e.id for e in near_strict} == {"infant", "toddler"}


def test_keyword_and_source():
    assert {e.id for e in apply_filters(EVENTS, FilterParams(keyword="lego"))} == {"school"}
    tagged = _event("z", [AgeBand.INFANT], miles=1, source="b")
    out = apply_filters([*EVENTS, tagged], FilterParams(sources={"b"}))
    assert {e.id for e in out} == {"z"}


def test_sort_by_distance_puts_unknown_last():
    out = apply_filters(EVENTS, FilterParams(sort=SortKey.DISTANCE))
    assert [e.id for e in out] == ["infant", "toddler", "school", "family", "online"]


def test_date_range():
    early = _event("early", [AgeBand.INFANT], miles=1, day=19)
    late = _event("late", [AgeBand.INFANT], miles=1, day=30)
    pool = [early, *EVENTS, late]
    out = apply_filters(
        pool,
        FilterParams(
            date_from=datetime(2026, 6, 20, 0, 0, tzinfo=PT),
            date_to=datetime(2026, 6, 25, 0, 0, tzinfo=PT),
        ),
    )
    ids = {e.id for e in out}
    assert "early" not in ids and "late" not in ids
