"""Persist the normalized event set to a JSON cache the web app reads.

Refresh is decoupled from the request path: ``kid-events refresh`` writes this
file; the web app loads it (and reloads when the file's mtime changes).
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .models import Event


class SourceStat(BaseModel):
    key: str
    name: str
    count: int
    error: str | None = None


class EventCache(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    events: list[Event]
    sources: list[SourceStat] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def cache_path() -> Path:
    override = os.environ.get("KID_EVENTS_CACHE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "data" / "cache" / "events.json"


def write_cache(cache: EventCache) -> Path:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cache.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_cache() -> EventCache | None:
    path = cache_path()
    if not path.exists():
        return None
    return EventCache.model_validate_json(path.read_text(encoding="utf-8"))
