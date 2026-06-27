import json
from pathlib import Path
from zoneinfo import ZoneInfo

from kid_events.models import AgeBand
from kid_events.sources.bibliocommons import parse_page

FIXTURE = Path(__file__).parent / "fixtures" / "bibliocommons_sccl.json"


def _synthetic(audience: dict[str, object]) -> dict:
    return {
        "events": {"items": ["e1"], "pagination": {"pages": 1, "page": 1}},
        "entities": {
            "events": {
                "e1": {
                    "id": "e1",
                    "definition": {
                        "start": "2026-06-20T10:30",
                        "end": "2026-06-20T11:00",
                        "title": "Baby Storytime",
                        "description": "<p>Songs &amp; rhymes</p>",
                        "branchLocationId": "MH",
                        "audienceIds": ["a1"],
                        "isCancelled": False,
                        "registrationInfo": {"provider": None},
                    },
                }
            },
            "eventAudiences": {"a1": audience},
            "locations": {"MH": {"id": "MH", "name": "Morgan Hill Library"}},
        },
    }


def test_timezone_tags_event_local_zone():
    # A library's local wall-clock time is tagged with its own zone, so Toronto
    # events read as Eastern (-04:00 in summer), not the default Pacific.
    payload = _synthetic({"id": "a1", "name": "Babies", "description": "Babies"})
    events = parse_page(
        payload,
        key="tpl",
        name="Toronto Public Library",
        subdomain="tpl",
        default_city="toronto",
        tz=ZoneInfo("America/Toronto"),
    )
    assert str(events[0].start) == "2026-06-20 10:30:00-04:00"


def _with_location(location: dict) -> list:
    payload = {
        "events": {"items": ["e1"], "pagination": {"pages": 1, "page": 1}},
        "entities": {
            "events": {
                "e1": {
                    "id": "e1",
                    "definition": {
                        "start": "2026-06-20T10:30",
                        "title": "Baby Storytime",
                        "description": "",
                        "branchLocationId": "B1",
                        "audienceIds": ["a1"],
                        "isCancelled": False,
                        "registrationInfo": {"provider": None},
                    },
                }
            },
            "eventAudiences": {"a1": {"id": "a1", "name": "Babies", "description": "Babies"}},
            "locations": {"B1": location},
        },
    }
    return parse_page(payload, key="tpl", name="TPL", subdomain="tpl", default_city="toronto")


def test_branch_coordinates_extracted():
    # isGeocoded is deliberately ignored — the centrePoint is still correct.
    event = _with_location(
        {
            "id": "B1",
            "name": "Fairview",
            "mapLocation": {"centrePoint": {"lat": 43.779, "lng": -79.347}, "isGeocoded": False},
            "address": {"city": "toronto"},
        }
    )[0]
    assert (event.lat, event.lon) == (43.779, -79.347)
    assert event.city == "Toronto"
    assert event.geo_precise is True
    assert event.location_name == "Fairview"


def test_branch_without_usable_coordinates():
    for location in (
        {"id": "B1", "name": "Fairview"},  # no mapLocation
        {"id": "B1", "name": "Fairview", "mapLocation": {"centrePoint": {"lat": 0, "lng": 0}}},
        {
            "id": "B1",
            "name": "Fairview",
            "mapLocation": {"centrePoint": {"lat": None, "lng": -79.3}},
        },
    ):
        event = _with_location(location)[0]
        assert event.lat is None and event.lon is None
        assert event.geo_precise is False


def test_parse_real_fixture_smoke():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    events = parse_page(
        payload, key="sccl", name="Santa Clara County Library", subdomain="sccl", default_city=""
    )
    assert events
    assert all(e.title for e in events)
    assert all(e.start.tzinfo is not None for e in events)
    assert all(e.id.startswith("sccl:") for e in events)
    assert all(e.url and "sccl.bibliocommons.com/events/" in e.url for e in events)
    # At least some events should carry kid-relevant age bands.
    assert any(any(b.is_kid for b in e.age_bands) for e in events)


def test_kids_prefix_does_not_force_school_age():
    # Using the clean description ("Babies").
    events = parse_page(
        _synthetic({"id": "a1", "name": "Kids: Babies", "description": "Babies"}),
        key="sccl",
        name="SCCLD",
        subdomain="sccl",
        default_city="",
    )
    assert events[0].age_bands == [AgeBand.INFANT]

    # Falling back to the name when description is missing still strips "Kids:".
    events = parse_page(
        _synthetic({"id": "a1", "name": "Kids: Babies", "description": None}),
        key="sccl",
        name="SCCLD",
        subdomain="sccl",
        default_city="",
    )
    assert events[0].age_bands == [AgeBand.INFANT]


def test_field_normalization():
    events = parse_page(
        _synthetic({"id": "a1", "name": "Kids: Babies", "description": "Babies"}),
        key="sccl",
        name="SCCLD",
        subdomain="sccl",
        default_city="",
    )
    event = events[0]
    assert event.description == "Songs & rhymes"
    assert event.location_name == "Morgan Hill Library"
    assert event.age_inferred is False
    assert event.registration_required is False
    assert event.start.hour == 10 and event.start.minute == 30
    assert event.end is not None
