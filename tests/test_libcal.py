from pathlib import Path

from kid_events.models import AgeBand
from kid_events.sources.libcal import parse_ical

FIXTURE = Path(__file__).parent / "fixtures" / "libcal_mountainview.ics"


def _events():
    text = FIXTURE.read_text(encoding="utf-8")
    return parse_ical(
        text,
        key="mountainview",
        name="Mountain View Public Library",
        default_city="mountain view",
    )


def _find(events, needle):
    return next(e for e in events if needle.lower() in e.title.lower())


def test_parse_ical_smoke():
    events = _events()
    assert len(events) > 50
    assert all(e.start.tzinfo is not None for e in events)
    assert all(e.age_inferred for e in events)  # LibCal age is always inferred
    assert all(e.id.startswith("mountainview:") for e in events)


def test_utc_times_convert_to_pacific():
    # "Public Works Spring Outdoor Storytime" is 17:30 UTC on a PDT date => 10:30.
    event = _find(_events(), "Outdoor Storytime")
    assert (event.start.hour, event.start.minute) == (10, 30)


def test_storytime_inference_and_categories():
    event = _find(_events(), "Outdoor Storytime")
    assert AgeBand.INFANT in event.age_bands
    assert AgeBand.TODDLER in event.age_bands
    assert AgeBand.PRESCHOOL in event.age_bands


def test_adult_event_has_no_kid_bands_and_registration():
    event = _find(_events(), "Nir Eyal")
    assert not any(b.is_kid for b in event.age_bands)
    assert event.location_name == "Online"
    assert event.registration_required is True
