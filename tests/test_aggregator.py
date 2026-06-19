from datetime import datetime
from zoneinfo import ZoneInfo

from kid_events.aggregator import aggregate, build_window, is_kid_relevant
from kid_events.models import AgeBand, Event

PT = ZoneInfo("America/Los_Angeles")


def _event(eid, title, bands, location="", cancelled=False):
    return Event(
        id=eid,
        source="Fake Library",
        source_key="fake",
        title=title,
        start=datetime(2026, 6, 20, 10, 0, tzinfo=PT),
        age_bands=list(bands),
        location_name=location,
        is_cancelled=cancelled,
    )


class FakeSource:
    key = "fake"
    name = "Fake Library"
    default_city = "mountain view"
    enabled = True

    def __init__(self, events: list[Event]) -> None:
        self._events = events

    def fetch(self, window_start: datetime, window_end: datetime) -> list[Event]:
        return list(self._events)


def test_is_kid_relevant():
    assert is_kid_relevant(_event("1", "x", [AgeBand.INFANT]))
    assert is_kid_relevant(_event("2", "x", [AgeBand.ALL_AGES]))
    assert not is_kid_relevant(_event("3", "x", [AgeBand.ADULT]))
    assert not is_kid_relevant(_event("4", "x", []))


def test_build_window():
    start, end = build_window(14)
    assert (start.hour, start.minute, start.second) == (0, 0, 0)
    assert (end - start).days == 14


def test_aggregate_filters_and_geocodes():
    source = FakeSource(
        [
            _event(
                "kid", "Toddler Time", [AgeBand.TODDLER], location="Mountain View Public Library"
            ),
            _event("adult", "Tax Help", [AgeBand.ADULT], location="Mountain View Public Library"),
            _event("closure", "Main Library Closed for Holiday", [AgeBand.ALL_AGES]),
            _event("online", "Virtual Storytime", [AgeBand.INFANT], location="Online"),
            _event("cancelled", "Baby Yoga", [AgeBand.INFANT], location="x", cancelled=True),
        ]
    )
    cache = aggregate(days=14, sources=[source])

    kept_ids = {e.id for e in cache.events}
    assert kept_ids == {"kid", "online"}  # adult, closure, cancelled dropped

    by_id = {e.id: e for e in cache.events}
    assert by_id["kid"].city == "Mountain View"
    assert by_id["kid"].distance_mi is not None and by_id["kid"].distance_mi < 1
    assert by_id["online"].distance_mi is None  # online -> no coordinates

    assert cache.sources[0].count == 2
    assert any("Sunnyvale" in note for note in cache.notes)  # disabled source reported
