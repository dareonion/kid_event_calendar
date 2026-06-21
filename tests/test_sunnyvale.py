from datetime import datetime
from zoneinfo import ZoneInfo

from kid_events.models import AgeBand
from kid_events.sources.sunnyvale_cms import (
    _event_id,
    _months_in_window,
    _parse_start,
    parse_raw_items,
)

PT = ZoneInfo("America/Los_Angeles")
WINDOW_S = datetime(2026, 6, 21, 0, 0, tzinfo=PT)
WINDOW_E = datetime(2026, 7, 5, 0, 0, tzinfo=PT)


def _raw(title, date_label, time, href="/Home/Components/Calendar/Event/100/129"):
    return {"title": title, "dateLabel": date_label, "time": time, "href": href}


def test_event_id():
    assert _event_id("/Home/Components/Calendar/Event/11900/129") == "11900"
    assert _event_id("no-id-here") == "no-id-here"


def test_months_in_window_spans_boundaries():
    assert _months_in_window(WINDOW_S, WINDOW_E) == [(2026, 6), (2026, 7)]
    year_end = _months_in_window(datetime(2026, 12, 20, tzinfo=PT), datetime(2027, 1, 3, tzinfo=PT))
    assert year_end == [(2026, 12), (2027, 1)]


def test_parse_start():
    assert _parse_start("Scheduled events, Tuesday, June 2, 2026", "7:00 PM") == datetime(
        2026, 6, 2, 19, 0, tzinfo=PT
    )
    midnight = _parse_start("Scheduled events, Monday, June 22, 2026", "")
    assert midnight is not None and (midnight.hour, midnight.minute) == (0, 0)
    assert _parse_start("no date at all", "") is None


def test_parse_raw_items_tags_filters_and_defaults():
    items = [
        _raw(
            "Baby Lapsit & Playtime",
            "Scheduled events, Thursday, June 25, 2026",
            "10:30 AM",
            "/Event/1/129",
        ),
        _raw(
            "Messy Art Monday", "Scheduled events, Monday, June 22, 2026", "3:00 PM", "/Event/2/129"
        ),
        _raw(
            "Belonging Tools for Parents (Online)",
            "Scheduled events, Tuesday, June 23, 2026",
            "7:00 PM",
            "/Event/3/129",
        ),
        _raw("Old Event", "Scheduled events, Monday, June 1, 2026", "10:00 AM", "/Event/4/129"),
    ]
    events = parse_raw_items(items, window_start=WINDOW_S, window_end=WINDOW_E)
    by_title = {e.title: e for e in events}

    assert "Old Event" not in by_title  # before the window
    assert by_title["Baby Lapsit & Playtime"].age_bands == [AgeBand.INFANT]
    # No inferable age on the kids calendar -> all-ages default (kept, not dropped).
    assert by_title["Messy Art Monday"].age_bands == [AgeBand.ALL_AGES]
    # Parent program keeps its ADULT tag (aggregator drops it later) and is online.
    parents = by_title["Belonging Tools for Parents (Online)"]
    assert AgeBand.ADULT in parents.age_bands
    assert parents.location_name == "Online"

    baby = by_title["Baby Lapsit & Playtime"]
    assert baby.url is not None and baby.url.startswith("https://www.library.sunnyvale.ca.gov/")
    assert all(e.id.startswith("sunnyvale:") for e in events)
    assert all(e.age_inferred for e in events)


def test_parse_raw_items_dedupes_same_event():
    item = _raw(
        "Toddler Time", "Scheduled events, Tuesday, June 23, 2026", "11:00 AM", "/Event/9/129"
    )
    events = parse_raw_items([item, dict(item)], window_start=WINDOW_S, window_end=WINDOW_E)
    assert len(events) == 1
