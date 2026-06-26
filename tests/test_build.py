import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kid_events.cache import EventCache, SourceStat
from kid_events.models import AgeBand, Event
from kid_events.web.build import branch_groups, build_site

PT = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def cache() -> EventCache:
    start = datetime.now(PT).replace(hour=0, minute=0, second=0, microsecond=0)
    baby = Event(
        id="mv:1",
        source="Mountain View Public Library",
        source_key="mountainview",
        title="Baby Storytime",
        description="Songs and rhymes.",
        url="https://example.org/e/1",
        start=start + timedelta(days=1, hours=10),
        location_name="Mountain View Public Library",
        city="Mountain View",
        lat=37.39,
        lon=-122.08,
        distance_mi=0.2,
        age_bands=[AgeBand.INFANT],
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
    return EventCache(
        generated_at=start,
        window_start=start,
        window_end=start + timedelta(days=14),
        events=[baby, lego],
        sources=[
            SourceStat(key="mountainview", name="Mountain View Public Library", count=1),
            SourceStat(key="sjpl", name="San Jose Public Library", count=1),
            SourceStat(key="sunnyvale", name="Sunnyvale Public Library", count=0, error="no feed"),
        ],
        notes=["Heads up: one source errored."],
    )


def _embedded_payload(html: str) -> dict:
    match = re.search(
        r'<script id="events-data" type="application/json">(.*?)</script>', html, re.S
    )
    assert match is not None
    return json.loads(match.group(1).replace("\\u003c", "<"))


def test_build_writes_site(tmp_path: Path, cache: EventCache) -> None:
    out = build_site(tmp_path / "site", cache=cache)

    index = out / "index.html"
    assert index.exists()
    for asset in ("style.css", "leaflet.css", "leaflet.js", "map.js", "app.js"):
        assert (out / "static" / asset).exists()
    # GitHub Pages should serve the output verbatim.
    assert (out / ".nojekyll").exists()


def test_embedded_payload_has_events_and_config(tmp_path: Path, cache: EventCache) -> None:
    html = (build_site(tmp_path / "site", cache=cache) / "index.html").read_text()

    # Events render in the no-JS fallback...
    assert "Baby Storytime" in html
    assert "LEGO Club" in html
    # ...and the same data is embedded for the client-side filter.
    payload = _embedded_payload(html)
    assert {e["title"] for e in payload["events"]} == {"Baby Storytime", "LEGO Club"}
    assert payload["default_radius"] == "far"
    assert payload["center"]["name"]
    assert any(b["value"] == "infant" and b["min"] == 0 for b in payload["bands"])
    # The errored source is still listed so the user knows it was attempted.
    assert any(s["key"] == "sunnyvale" and s["error"] for s in payload["sources"])


def test_branch_groups_and_dropdown(tmp_path: Path, cache: EventCache) -> None:
    groups = branch_groups(cache)
    sources = {g["source"] for g in groups}
    # Only sources that have a named branch show up.
    assert "Mountain View Public Library" in sources
    assert "Sunnyvale Public Library" not in sources  # no named branch
    mv = next(g for g in groups if g["source"] == "Mountain View Public Library")
    assert any(
        o["value"] == "Mountain View Public Library" and o["label"].endswith("(1)")
        for o in mv["options"]
    )

    html = (build_site(tmp_path / "site", cache=cache) / "index.html").read_text()
    assert 'name="branch"' in html
    assert "<optgroup" in html


def test_build_without_cache_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KID_EVENTS_CACHE", str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError):
        build_site(tmp_path / "site")


def test_script_tag_cannot_be_broken_by_event_text(tmp_path: Path, cache: EventCache) -> None:
    # A literal "</script>" in event data must not close the data block early.
    cache.events[0].description = "Sneaky </script><script>alert(1)</script>"
    html = (build_site(tmp_path / "site", cache=cache) / "index.html").read_text()
    data_block = re.search(
        r'<script id="events-data" type="application/json">(.*?)</script>', html, re.S
    )
    assert data_block is not None
    assert "</script>" not in data_block.group(1)
    # And it still parses back to the original text.
    payload = json.loads(data_block.group(1).replace("\\u003c", "<"))
    descs = [e["description"] for e in payload["events"]]
    assert "Sneaky </script><script>alert(1)</script>" in descs
