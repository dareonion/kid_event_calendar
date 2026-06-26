from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from kid_events.cache import EventCache, SourceStat, write_cache
from kid_events.models import AgeBand, Event

PT = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("KID_EVENTS_CACHE", str(tmp_path / "events.json"))
    start = datetime.now(PT).replace(hour=0, minute=0, second=0, microsecond=0)
    baby = Event(
        id="mv:1",
        source="Mountain View Public Library",
        source_key="mountainview",
        title="Baby Storytime",
        description="Songs and rhymes for the littlest listeners.",
        url="https://example.org/e/1",
        start=start + timedelta(days=1, hours=10),
        location_name="Mountain View Public Library",
        city="Mountain View",
        lat=37.39,
        lon=-122.08,
        distance_mi=0.2,
        age_bands=[AgeBand.INFANT],
        age_inferred=True,
    )
    lego = Event(
        id="sj:2",
        source="San Jose Public Library",
        source_key="sjpl",
        title="LEGO Club",
        start=start + timedelta(days=2, hours=15),
        city="San Jose",
        lat=37.34,
        lon=-121.89,
        distance_mi=11.0,
        age_bands=[AgeBand.SCHOOL_AGE],
    )
    write_cache(
        EventCache(
            generated_at=start,
            window_start=start,
            window_end=start + timedelta(days=14),
            events=[baby, lego],
            sources=[
                SourceStat(key="mountainview", name="Mountain View Public Library", count=1),
                SourceStat(key="sjpl", name="San Jose Public Library", count=1),
            ],
            notes=["Disabled sources: Sunnyvale Public Library"],
        )
    )
    from kid_events.web.app import _state, app

    _state["mtime"] = None  # force a cache reload for this test's file
    return TestClient(app)


def test_index_renders_events(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "Kid Event Calendar" in response.text
    assert "Baby Storytime" in response.text
    assert "LEGO Club" in response.text
    assert "Sunnyvale" in response.text  # disabled-source note shown


def test_age_filter(client: TestClient):
    response = client.get("/events", params={"age": "8 months"})
    assert "Baby Storytime" in response.text
    assert "LEGO Club" not in response.text


def test_distance_filter(client: TestClient):
    response = client.get("/events", params={"radius": "mv"})  # ~5 mi
    assert "Baby Storytime" in response.text
    assert "LEGO Club" not in response.text  # 11 mi away


def test_keyword_filter(client: TestClient):
    response = client.get("/events", params={"keyword": "lego"})
    assert "LEGO Club" in response.text
    assert "Baby Storytime" not in response.text


def test_branch_filter(client: TestClient):
    response = client.get("/events", params={"branch": "Mountain View Public Library"})
    assert "Baby Storytime" in response.text  # its location_name matches
    assert "LEGO Club" not in response.text  # different branch


def test_branch_dropdown_present(client: TestClient):
    response = client.get("/")
    assert 'name="branch"' in response.text
    assert "Mountain View Public Library" in response.text  # offered as a branch option


def test_map_view(client: TestClient):
    response = client.get("/events", params={"view": "map"})
    assert response.status_code == 200
    assert 'id="map"' in response.text
    assert 'id="map-data"' in response.text  # events embedded as JSON for Leaflet
    # Both located events' cities should appear in the embedded marker data.
    assert "Mountain View" in response.text
    assert "San Jose" in response.text
