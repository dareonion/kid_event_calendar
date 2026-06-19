from datetime import datetime
from zoneinfo import ZoneInfo

from kid_events.models import AgeBand, Event

PT = ZoneInfo("America/Los_Angeles")


def test_age_band_metadata():
    assert AgeBand.INFANT.min_months == 0
    assert AgeBand.INFANT.max_months == 17
    assert AgeBand.PRESCHOOL.label.startswith("Preschool")
    assert AgeBand.ADULT.is_kid is False
    assert AgeBand.ALL_AGES.is_kid is True


def test_event_defaults_and_helpers():
    event = Event(
        id="1",
        source="Mountain View Public Library",
        source_key="mountainview",
        title="Baby Storytime",
        start=datetime(2026, 6, 20, 10, 0, tzinfo=PT),
        age_bands=[AgeBand.INFANT, AgeBand.ALL_AGES],
    )
    assert event.has_known_location() is False
    assert event.age_band_labels == [AgeBand.INFANT.label, AgeBand.ALL_AGES.label]

    located = event.model_copy(update={"lat": 37.4, "lon": -122.1})
    assert located.has_known_location() is True
