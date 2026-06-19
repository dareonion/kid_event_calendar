"""Fetch every source, normalize, geolocate, and assemble the event cache."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .branches import load_location_book
from .cache import EventCache, SourceStat
from .geo import haversine_miles
from .models import Event
from .sources.base import PACIFIC, Source
from .sources.registry import ALL_SOURCES, active_sources

# Administrative entries (holiday closures) are tagged for every audience but
# are not real programs, so they are dropped.
_CLOSURE_RE = re.compile(r"(library closed|closed for|\bclosure\b|holiday hours)", re.IGNORECASE)


def build_window(days: int) -> tuple[datetime, datetime]:
    """Window from the start of today through ``days`` later, Pacific time."""
    start = datetime.now(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=days)


def is_kid_relevant(event: Event) -> bool:
    return any(band.is_kid for band in event.age_bands)


def _locate(event: Event, default_city: str) -> Event:
    book = load_location_book()
    lat, lon, city = book.resolve(event.location_name, default_city)
    distance = (
        round(haversine_miles(book.center.lat, book.center.lon, lat, lon), 1)
        if lat is not None and lon is not None
        else None
    )
    return event.model_copy(update={"lat": lat, "lon": lon, "city": city, "distance_mi": distance})


def aggregate(days: int = 14, sources: list[Source] | None = None) -> EventCache:
    """Build the event cache from the given (or all active) sources."""
    sources = sources if sources is not None else active_sources()
    window_start, window_end = build_window(days)

    events: list[Event] = []
    stats: list[SourceStat] = []
    for source in sources:
        try:
            fetched = source.fetch(window_start, window_end)
        except Exception as exc:
            # Report a per-source failure and keep going with the others.
            stats.append(SourceStat(key=source.key, name=source.name, count=0, error=str(exc)))
            continue
        kept = [
            _locate(event, source.default_city)
            for event in fetched
            if not event.is_cancelled
            and is_kid_relevant(event)
            and not _CLOSURE_RE.search(event.title)
        ]
        events.extend(kept)
        stats.append(SourceStat(key=source.key, name=source.name, count=len(kept)))

    events.sort(key=lambda event: event.start)

    notes: list[str] = []
    disabled = [s.name for s in ALL_SOURCES if not s.enabled]
    if disabled:
        notes.append("Disabled sources (feed not yet wired): " + ", ".join(disabled))

    return EventCache(
        generated_at=datetime.now(PACIFIC),
        window_start=window_start,
        window_end=window_end,
        events=events,
        sources=stats,
        notes=notes,
    )
