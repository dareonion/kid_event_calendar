import json
from pathlib import Path

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
