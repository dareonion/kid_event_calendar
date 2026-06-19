from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kid_events.cache import EventCache, SourceStat, cache_path, load_cache, write_cache
from kid_events.models import AgeBand, Event

PT = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def _cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "events.json"
    monkeypatch.setenv("KID_EVENTS_CACHE", str(target))
    return target


def _sample_cache() -> EventCache:
    event = Event(
        id="fake:1",
        source="Fake Library",
        source_key="fake",
        title="Toddler Time",
        start=datetime(2026, 6, 20, 10, 0, tzinfo=PT),
        age_bands=[AgeBand.TODDLER],
        distance_mi=2.3,
    )
    return EventCache(
        generated_at=datetime(2026, 6, 19, 8, 0, tzinfo=PT),
        window_start=datetime(2026, 6, 19, 0, 0, tzinfo=PT),
        window_end=datetime(2026, 7, 3, 0, 0, tzinfo=PT),
        events=[event],
        sources=[SourceStat(key="fake", name="Fake Library", count=1)],
        notes=["hello"],
    )


def test_cache_round_trip(_cache_file: Path):
    assert load_cache() is None  # nothing written yet

    path = write_cache(_sample_cache())
    assert path == cache_path()

    loaded = load_cache()
    assert loaded is not None
    assert len(loaded.events) == 1
    assert loaded.events[0].age_bands == [AgeBand.TODDLER]
    assert loaded.events[0].start.tzinfo is not None
    assert loaded.sources[0].count == 1
    assert loaded.notes == ["hello"]
