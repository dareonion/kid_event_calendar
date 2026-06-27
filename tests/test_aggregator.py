from datetime import datetime
from zoneinfo import ZoneInfo

from kid_events import aggregator
from kid_events.aggregator import _locate, aggregate, build_window, is_kid_relevant
from kid_events.branches import Coord, LocationBook
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
    # All registered sources are active now, so there is no disabled-source note.
    assert cache.notes == []


def test_locate_precedence(monkeypatch):
    book = LocationBook(
        center_name="Mountain View",
        center=Coord(lat=37.3894, lon=-122.0819),
        cities={"mountain view": Coord(lat=37.3894, lon=-122.0819)},
        branches={"miss": {"burnhamthorpe library": Coord(lat=43.6005, lon=-79.6402)}},
    )
    monkeypatch.setattr(aggregator, "load_location_book", lambda: book)
    start = datetime(2026, 6, 20, 10, 0, tzinfo=PT)

    # 1. Coordinates the source already supplied are kept verbatim.
    supplied = Event(
        id="1",
        source="TPL",
        source_key="tpl",
        title="x",
        start=start,
        location_name="Fairview",
        lat=43.779,
        lon=-79.347,
        city="Toronto",
        geo_precise=True,
    )
    out1 = _locate(supplied, "toronto")
    assert (out1.lat, out1.lon, out1.city) == (43.779, -79.347, "Toronto")
    assert out1.geo_precise is True
    assert out1.distance_mi and out1.distance_mi > 1000  # far from Mountain View

    # 2. A per-branch table entry wins over the city centroid.
    miss = Event(
        id="2",
        source="Mississauga",
        source_key="miss",
        title="x",
        start=start,
        location_name="Burnhamthorpe Library",
    )
    out2 = _locate(miss, "mississauga")
    assert (out2.lat, out2.lon) == (43.6005, -79.6402)
    assert out2.city == "Mississauga" and out2.geo_precise is True

    # 3. Otherwise fall back to the city centroid (not precise).
    mv = Event(
        id="3",
        source="MV",
        source_key="fake",
        title="x",
        start=start,
        location_name="Mountain View Public Library",
    )
    out3 = _locate(mv, "mountain view")
    assert out3.city == "Mountain View" and out3.geo_precise is False
